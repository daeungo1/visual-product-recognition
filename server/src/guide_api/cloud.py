"""Cloud application service: ownership, conditional writes and evidence, no local fallback."""

import hashlib
import json
import re
import secrets
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException

from guide_api.cloud_contracts import CloudEvent, CloudGuide, DraftRequest, IdentifyRequest
from guide_api.images import ImageInput, decode_image, image_bytes

TOKEN_LIFETIME = 86400
PROOF_LIFETIME = 30
MAX_REPLAYS = 256
MAX_CAS_ATTEMPTS = 5


class NotFound(Exception):
    """Adapter point read did not find an item."""


class Conflict(Exception):
    """Adapter conditional create, replace or delete lost a race."""


class Documents(Protocol):
    def read(self, container: str, item_id: str) -> dict: ...
    def create(self, container: str, document: dict) -> None: ...
    def replace(self, container: str, document: dict, etag: str) -> None: ...
    def delete(self, container: str, item_id: str, etag: str) -> None: ...
    def list(self, container: str, kind: str) -> list[dict]: ...
    def ready(self) -> None: ...


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def published(document: dict) -> bool:
    return document.get("review_status") == "reviewed" and (
        document.get("demo", document.get("guide", {}).get("demo", False))
        or bool(document.get("source_url") and document.get("model"))
    )


def ocr_matches(expected: str, observed: str) -> bool:
    # Whole normalized display states avoid substring/numeric-boundary false positives.
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).upper()).strip()

    return normalize(expected) == normalize(observed)


class PairLimiter:
    def __init__(self, clock: Callable[[], float]):
        self.clock = clock
        self.lock = threading.Lock()
        self.clients: OrderedDict[str, deque] = OrderedDict()
        self.global_attempts: deque = deque()

    def check(self, address: str) -> None:
        now = self.clock()
        with self.lock:
            if address not in self.clients and len(self.clients) >= 1024:
                self.clients.popitem(last=False)
            queue = self.clients.setdefault(address, deque())
            self.clients.move_to_end(address)
            for attempts in (queue, self.global_attempts):
                while attempts and attempts[0] <= now - 60:
                    attempts.popleft()
            if len(queue) >= 10 or len(self.global_attempts) >= 120:
                raise HTTPException(
                    429,
                    "Pairing attempt limit reached.",
                    headers={"Retry-After": "60"},
                )
            queue.append(now)
            self.global_attempts.append(now)


class CloudService:
    def __init__(
        self,
        documents: Documents,
        assets,
        search,
        embedder,
        ai,
        *,
        clock: Callable[[], float] = time.time,
        verify_deployment: str = "guide-verify",
    ):
        self.documents, self.assets, self.search = documents, assets, search
        self.embedder, self.ai, self.clock = embedder, ai, clock
        self.verify_deployment = verify_deployment
        self.limiter = PairLimiter(clock)
        self.work_slots = threading.BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visual-guide-ai")
        self.ai_slots = threading.BoundedSemaphore(1)
        self.ai_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visual-guide-vlm")

    def run_work(self, operation: Callable, *, timeout: float = 90):
        return self._run_bounded(operation, self.work_slots, self.executor, timeout)

    def run_ai(self, operation: Callable, *, timeout: float = 40):
        return self._run_bounded(operation, self.ai_slots, self.ai_executor, timeout)

    @staticmethod
    def _run_bounded(operation, slots, executor, timeout):
        if not slots.acquire(blocking=False):
            raise HTTPException(429, "AI worker busy.", headers={"Retry-After": "2"})

        def execute():
            try:
                return operation()
            finally:
                slots.release()

        try:
            future = executor.submit(execute)
        except RuntimeError:
            slots.release()
            raise HTTPException(503, "AI worker is shutting down.") from None
        # A timed-out CPU/SDK operation cannot be forcefully stopped safely. Keep the slot
        # until it truly ends, so retries never start overlapping model calls.
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as error:
            raise HTTPException(504, "Cloud AI operation exceeded its deadline.") from error

    def ready(self) -> dict:
        def check():
            self.embedder.load()
            self.documents.ready()
            return self.search.ready() or {}

        search = self.run_work(check)
        return {
            "status": "ready",
            "storage": "cosmos",
            "embedding_model": self.embedder.version,
            "search_document_count": search.get("document_count"),
        }

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.ai_executor.shutdown(wait=True, cancel_futures=True)
        for adapter in (self.ai, self.search, self.assets, self.documents):
            close = getattr(adapter, "close", None)
            if close:
                close()
        credential = getattr(self, "credential", None)
        if credential:
            credential.close()

    def pair(self, code: str, address: str) -> dict:
        self.limiter.check(address)
        try:
            invite = self.documents.read("invites", token_hash(code))
            if not self.clock() < invite["expires_at"] <= self.clock() + 7 * 86400 or invite.get(
                "scope"
            ) not in {
                "device",
                "admin",
            }:
                raise HTTPException(401, "Invalid or expired pairing code.")
            self.documents.delete("invites", invite["id"], invite["_etag"])
        except (NotFound, Conflict) as error:
            raise HTTPException(401, "Invalid or consumed pairing code.") from error
        token = secrets.token_urlsafe(48)
        device_id = str(uuid4())
        self.documents.create(
            "devices",
            {
                "id": token_hash(token),
                "kind": "device",
                "device_id": device_id,
                "scope": invite["scope"],
                "expires_at": self.clock() + TOKEN_LIFETIME,
                "ttl": TOKEN_LIFETIME,
            },
        )
        return {
            "token_type": "Bearer",
            "access_token": token,
            "expires_in": TOKEN_LIFETIME,
            "device_id": device_id,
            "scope": invite["scope"],
        }

    def authenticate(self, authorization: str | None) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required.")
        token = authorization[7:]
        if not 32 <= len(token) <= 256:
            raise HTTPException(401, "Invalid bearer token.")
        try:
            device = self.documents.read("devices", token_hash(token))
        except NotFound as error:
            raise HTTPException(401, "Invalid bearer token.") from error
        if device["expires_at"] <= self.clock() or device.get("scope") not in {"device", "admin"}:
            raise HTTPException(401, "Expired or revoked bearer token.")
        return device

    def registered(self, item_id: str) -> dict:
        try:
            document = self.documents.read("catalog", item_id)
        except NotFound as error:
            raise HTTPException(404, "Asset not registered.") from error
        if not published(document):
            raise HTTPException(404, "Asset is not reviewed for publication.")
        return document

    def guide(self, guide_id: str) -> dict:
        return CloudGuide.model_validate(self.registered(f"guide:{guide_id}")["guide"]).model_dump()

    def catalog(self) -> dict:
        guides = [
            CloudGuide.model_validate(doc["guide"]).model_dump()
            for doc in self.documents.list("catalog", "guide")
            if published(doc)
        ]
        real = any(not guide["demo"] for guide in guides)
        return {
            "demo": not real,
            "real_product_assets_registered": real,
            "guides": guides,
            "notice": "Synthetic assets are labeled demo. Candidates always require confirmation.",
        }

    def model(self, target_id: str) -> dict:
        target = self.registered(f"target:{target_id}")
        panel = target["panel_map"]

        def rectangle(values):
            return dict(zip(("left", "top", "right", "bottom"), values, strict=True))

        return {
            "id": target_id,
            "reference_width_m": panel["physical_width_meters"],
            "reference_image_url": f"/v1/models/{target_id}/reference",
            "image_width": panel["width_pixels"],
            "image_height": panel["height_pixels"],
            "display": rectangle(panel["display"]),
            "buttons": {key: rectangle(value) for key, value in panel["buttons"].items()},
        }

    def reference(self, target_id: str) -> ImageInput:
        target = self.registered(f"target:{target_id}")
        return image_bytes(self.assets.read(target["reference_blob"]))

    @staticmethod
    def state(document: dict) -> dict:
        guide, index = document["guide"], document["step_index"]
        return {
            "id": document["id"],
            "guide_id": guide["id"],
            "step_index": index,
            "current_step_id": guide["steps"][index]["id"] if index < len(guide["steps"]) else None,
            "finished": index == len(guide["steps"]),
            "demo": guide["demo"],
            "last_source": document["last_source"],
        }

    def owned(self, session_id: str, device: dict) -> dict:
        try:
            document = self.documents.read("sessions", session_id)
        except NotFound as error:
            raise HTTPException(404, "Session not found.") from error
        if document["owner_id"] != device["device_id"]:
            raise HTTPException(404, "Session not found.")
        return document

    def start(self, guide_id: str, device: dict) -> dict:
        document = {
            "id": str(uuid4()),
            "kind": "session",
            "owner_id": device["device_id"],
            "guide": self.guide(guide_id),
            "step_index": 0,
            "last_source": None,
            "events": {},
            "proofs": {},
            "created_at": self.clock(),
        }
        self.documents.create("sessions", document)
        return self.state(document)

    @staticmethod
    def current_step(document: dict, step_id: str) -> dict:
        guide, index = document["guide"], document["step_index"]
        if index >= len(guide["steps"]) or guide["steps"][index]["id"] != step_id:
            raise HTTPException(409, "Only the current unfinished step can be used.")
        return guide["steps"][index]

    def advance(self, session_id: str, device: dict, event: CloudEvent) -> dict:
        payload = json.dumps(event.model_dump(), sort_keys=True, separators=(",", ":"))
        for _ in range(MAX_CAS_ATTEMPTS):
            document = self.owned(session_id, device)
            prior = document["events"].get(event.event_id)
            if prior:
                if prior["payload"] != payload:
                    raise HTTPException(409, "Event ID reused for a different payload.")
                return prior["response"]
            step = self.current_step(document, event.step_id)
            if len(document["events"]) >= MAX_REPLAYS:
                raise HTTPException(409, "Session event ledger is full; start a new session.")
            if event.source == "ocr" and not ocr_matches(
                step["expected_display"],
                event.observed_text,
            ):
                raise HTTPException(409, "OCR does not match the authoritative expected display.")
            if event.source == "vlm":
                proof = document["proofs"].get(event.verification_id)
                if (
                    not proof
                    or proof["step_id"] != event.step_id
                    or (
                        proof["step_index"] != document["step_index"]
                        or proof["expires_at"] <= self.clock()
                    )
                ):
                    raise HTTPException(409, "Verification proof is stale, consumed or wrong-step.")
            document["step_index"] += 1
            document["last_source"] = event.source
            document["proofs"] = {}
            result = self.state(document)
            document["events"][event.event_id] = {"payload": payload, "response": result}
            try:
                self.documents.replace("sessions", document, document["_etag"])
                return result
            except Conflict:
                continue
        raise HTTPException(409, "Concurrent session update; retry the same event.")

    def verify(self, session_id: str, device: dict, step_id: str, encoded: str) -> dict:
        document = self.owned(session_id, device)
        step = self.current_step(document, step_id)
        image = decode_image(encoded)
        verdict = self.run_ai(lambda: self.ai.verify(image, step["expected_display"]))
        if verdict.get("status") not in {"pass", "fail", "unsure"}:
            raise HTTPException(503, "Verification provider returned an invalid verdict.")
        result = {
            "status": verdict["status"],
            "step_id": step_id,
            "reason": str(verdict["reason"])[:500],
            "verification_id": None,
            "expires_in": 0,
            "model_deployment": self.verify_deployment,
        }
        for _ in range(MAX_CAS_ATTEMPTS):
            current = self.owned(session_id, device)
            self.current_step(current, step_id)
            if current["step_index"] != document["step_index"]:
                raise HTTPException(409, "Step changed while verification was running.")
            if verdict["status"] != "pass":
                return result
            proof_id = secrets.token_urlsafe(24)
            current["proofs"] = {
                key: value
                for key, value in current["proofs"].items()
                if value["expires_at"] > self.clock()
            }
            if len(current["proofs"]) >= 4:
                raise HTTPException(429, "Too many unconsumed verification proofs.")
            current["proofs"][proof_id] = {
                "step_id": step_id,
                "step_index": current["step_index"],
                "expires_at": self.clock() + PROOF_LIFETIME,
            }
            try:
                self.documents.replace("sessions", current, current["_etag"])
                return {**result, "verification_id": proof_id, "expires_in": PROOF_LIFETIME}
            except Conflict:
                continue
        raise HTTPException(409, "Concurrent session update during verification.")

    def identify(self, body: IdentifyRequest) -> dict:
        image = decode_image(body.image_base64)
        candidates: dict[str, dict] = {}
        vector = self.run_work(lambda: self.embedder.embed(image), timeout=45)
        hits = self.search.query(vector, body.category, body.target_kind)
        for hit in hits[:12]:
            target_id = hit["target_id"]
            if target_id in candidates:
                continue
            try:
                target = self.registered(f"target:{target_id}")
            except HTTPException as error:
                if error.status_code == 404:
                    continue
                raise
            if (target["category"], target["target_kind"]) != (body.category, body.target_kind):
                continue
            target["search_score"] = float(hit["score"])
            candidates[target_id] = target
            if len(candidates) == 4:
                break
        references = [(target_id, self.reference(target_id)) for target_id in candidates]
        matches = self.run_ai(lambda: self.ai.identify(image, references)) if candidates else []
        results, seen_products = [], set()
        for target_id, target in candidates.items():
            if target_id not in matches or target["product_id"] in seen_products:
                continue
            seen_products.add(target["product_id"])
            results.append(
                {
                    key: target[key]
                    for key in (
                        "product_id",
                        "model",
                        "target_id",
                        "guide_ids",
                        "search_score",
                        "demo",
                    )
                }
            )
        return {
            "status": "candidates" if results else "unknown",
            "requires_confirmation": bool(results),
            "candidates": results,
            "provider": "siglip2-search-vlm",
        }

    def reindex(self) -> dict:
        return self.run_work(self._reindex)

    def _reindex(self) -> dict:
        documents = []
        for target in self.documents.list("catalog", "target"):
            if not published(target):
                continue
            image = self.reference(target["target_id"])
            documents.append(
                {
                    "id": target["target_id"],
                    "target_id": target["target_id"],
                    "product_id": target["product_id"],
                    "category": target["category"],
                    "target_kind": target["target_kind"],
                    "model_version": self.embedder.version,
                    "embedding": self.embedder.embed(image),
                }
            )
            if len(documents) > 1000:
                raise HTTPException(413, "PoC reindex limit is 1000 targets.")
        for offset in range(0, len(documents), 100):
            self.search.upload(documents[offset : offset + 100])
        return {
            "indexed": len(documents),
            "dimensions": self.embedder.dimensions,
            "model_version": self.embedder.version,
        }

    def draft(self, body: DraftRequest) -> dict:
        result = self.run_ai(lambda: self.ai.draft(body))
        return {
            **result,
            "review_status": "draft",
            "source_url": str(body.source_url),
            "model": body.model,
        }
