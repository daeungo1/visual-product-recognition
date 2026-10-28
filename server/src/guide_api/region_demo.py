"""Local-only Foundry region proposal demo: `python -m guide_api.region_demo`.

Binds to 127.0.0.1, uses the developer's Entra login, stores nothing and is not a
production service. Phone access is intentionally not provided.
"""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from guide_api.region_proposal import propose

PAGE = Path(__file__).with_name("region_demo.html")
MAX_IMAGE_BYTES = 4_000_000
PNG, JPEG = b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"


def parse_components(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not 1 <= len(names) <= 8 or any(len(name) > 40 for name in names):
        raise HTTPException(422, "Provide 1-8 component names up to 40 characters.")
    return names


def create_app(endpoint: str | None = None, deployment: str | None = None, proposer=propose):
    app = FastAPI(title="Region proposal local demo")
    endpoint = endpoint or os.getenv("FOUNDRY_ENDPOINT", "")
    deployment = deployment or os.getenv("FOUNDRY_DEPLOYMENT", "gpt-6-1-terra")

    @app.get("/")
    def page():
        return FileResponse(PAGE, media_type="text/html")

    @app.post("/propose")
    async def propose_regions(request: Request, components: str):
        if not endpoint.startswith("https://"):
            raise HTTPException(503, "FOUNDRY_ENDPOINT is not configured.")
        names = parse_components(components)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "Image exceeds 4 MB.")
        data = bytes(data)
        if not (data.startswith(PNG) or data.startswith(JPEG)):
            raise HTTPException(415, "Only PNG or JPEG images are accepted.")
        try:
            regions = await run_in_threadpool(proposer, data, names, endpoint, deployment)
        except Exception as error:
            raise HTTPException(502, f"Model call failed ({type(error).__name__}).") from error
        return {
            "model": deployment,
            "status": "draft_needs_human_review",
            "regions": [
                {"component": r.component, "point": r.point, "box": r.box} for r in regions
            ],
            "missing": [n for n in names if n not in {r.component for r in regions}],
        }

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8890)
