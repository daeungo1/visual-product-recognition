"""SDK boundary tests; all transport/inference calls are replaced, never cloud smoke tests."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosAccessConditionFailedError
from fastapi import HTTPException
from openai import APITimeoutError
from test_cloud import IMAGE

from guide_api.azure_adapters import (
    MODEL_VERSION,
    BlobAssets,
    CosmosDocuments,
    ImageSearch,
    VisionAI,
    search_index,
)
from guide_api.cloud import Conflict
from guide_api.images import MAX_IMAGE_BYTES, decode_image


def cosmos(container):
    adapter = CosmosDocuments.__new__(CosmosDocuments)
    adapter.database = SimpleNamespace(get_container_client=lambda _: container)
    return adapter


def test_cosmos_partition_and_etag_are_sent_to_sdk():
    container = Mock()
    adapter = cosmos(container)
    adapter.read("sessions", "session-id")
    container.read_item.assert_called_once_with("session-id", partition_key="session-id")
    document = {"id": "session-id", "step_index": 1}
    adapter.replace("sessions", document, "etag-1")
    container.replace_item.assert_called_once_with(
        item="session-id",
        body=document,
        etag="etag-1",
        match_condition=MatchConditions.IfNotModified,
    )
    adapter.delete("invites", "hashed-code", "etag-2")
    container.delete_item.assert_called_once_with(
        "hashed-code",
        partition_key="hashed-code",
        etag="etag-2",
        match_condition=MatchConditions.IfNotModified,
    )


def test_cosmos_etag_failure_is_a_conflict_not_an_unconditional_retry():
    container = Mock()
    container.replace_item.side_effect = CosmosAccessConditionFailedError(status_code=412)
    with pytest.raises(Conflict):
        cosmos(container).replace("sessions", {"id": "id"}, "stale")
    assert container.replace_item.call_count == 1


def test_blob_reference_download_uses_explicit_bounded_sdk_range():
    blob = Mock()
    blob.get_blob_properties.return_value.size = 100
    blob.download_blob.return_value.readall.return_value = b"reference"
    adapter = BlobAssets.__new__(BlobAssets)
    adapter.container = Mock()
    adapter.container.get_blob_client.return_value = blob
    assert adapter.read("reference.png") == b"reference"
    blob.download_blob.assert_called_once_with(
        offset=0, length=MAX_IMAGE_BYTES + 1, max_concurrency=1,
    )


def test_oversized_blob_reference_is_rejected_before_download():
    blob = Mock()
    blob.get_blob_properties.return_value.size = MAX_IMAGE_BYTES + 1
    adapter = BlobAssets.__new__(BlobAssets)
    adapter.container = Mock()
    adapter.container.get_blob_client.return_value = blob
    with pytest.raises(HTTPException) as raised:
        adapter.read("oversized.png")
    assert raised.value.status_code == 413
    blob.download_blob.assert_not_called()


def test_search_schema_and_query_use_actual_vector_and_filters():
    index = search_index("product-images")
    fields = {field.name: field for field in index.fields}
    assert fields["embedding"].vector_search_dimensions == 768
    assert index.vector_search.algorithms[0].parameters.metric == "cosine"
    assert fields["category"].filterable and fields["target_kind"].filterable
    adapter = ImageSearch.__new__(ImageSearch)
    adapter.client = Mock()
    adapter.client.search.return_value = [{"target_id": "registered-id", "@search.score": 0.7}]
    result = adapter.query([1.0] + [0.0] * 767, "aircon", "remote")
    assert result == [{"target_id": "registered-id", "score": 0.7}]
    arguments = adapter.client.search.call_args.kwargs
    assert MODEL_VERSION in arguments["filter"]
    assert "category eq 'aircon'" in arguments["filter"]
    assert "target_kind eq 'remote'" in arguments["filter"]
    assert len(arguments["vector_queries"][0].vector) == 768


def test_readiness_accepts_and_transparently_reports_prepared_empty_index():
    adapter = ImageSearch.__new__(ImageSearch)
    adapter.index = "product-images"
    adapter.index_client = Mock()
    adapter.index_client.get_index.side_effect = AssertionError("Runtime lacks schema permission")
    adapter.client = Mock()
    adapter.client.get_document_count.return_value = 0
    adapter.client.search.return_value = []
    assert adapter.ready() == {"document_count": 0}
    adapter.index_client.get_index.assert_not_called()
    adapter.client.search.assert_called_once()


def vision(content=None, refusal=None, finish_reason="stop"):
    adapter = VisionAI.__new__(VisionAI)
    adapter.verify_deployment = "guide-verify"
    adapter.author_deployment = "guide-author"
    create = Mock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(content), refusal=refusal),
                    finish_reason=finish_reason,
                )
            ]
        )
    )
    adapter.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return adapter, create


def test_actual_vlm_request_contains_image_and_authoritative_state():
    adapter, create = vision({"status": "pass", "reason": "Visible state matches"})
    assert adapter.verify(decode_image(IMAGE), "TEMP 24")["status"] == "pass"
    args = create.call_args.kwargs
    assert args["model"] == "guide-verify"
    assert args["max_completion_tokens"] == 512 and args["reasoning_effort"] == "none"
    assert args["response_format"]["json_schema"]["strict"] is True
    contents = args["messages"][1]["content"]
    assert "TEMP 24" in contents[0]["text"]
    assert contents[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("mode", ["refusal", "truncated", "timeout", "bad-verdict"])
def test_ai_errors_refusals_and_invalid_output_cannot_pass(mode):
    adapter, create = vision({"status": "not-a-verdict", "reason": "Invalid"})
    if mode == "refusal":
        adapter, create = vision(refusal="Cannot verify")
    elif mode == "truncated":
        adapter, create = vision(finish_reason="length")
    elif mode == "timeout":
        create.side_effect = APITimeoutError(request=httpx.Request("POST", "https://example.org"))
    with pytest.raises(HTTPException) as raised:
        adapter.verify(decode_image(IMAGE), "POWER ON")
    assert raised.value.status_code == (504 if mode == "timeout" else 503)


def test_identify_uses_query_plus_registered_reference_and_removes_invented_ids():
    adapter, create = vision({"matched_target_ids": ["invented", "known", "known"]})
    image = decode_image(IMAGE)
    assert adapter.identify(image, [("known", image)]) == ["known"]
    content = create.call_args.kwargs["messages"][1]["content"]
    assert len([item for item in content if item["type"] == "image_url"]) == 2
    assert (
        "known"
        in create.call_args.kwargs["response_format"]["json_schema"]["schema"]["properties"][
            "matched_target_ids"
        ]["items"]["enum"]
    )
