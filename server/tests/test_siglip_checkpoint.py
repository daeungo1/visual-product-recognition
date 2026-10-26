"""The pinned fixed-resolution SigLIP2 checkpoint uses the Siglip architecture."""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from guide_api.azure_adapters import SiglipEmbedder


def checkpoint_modules(monkeypatch, model_type="siglip", dimensions=768):
    calls = {}
    processor = object()

    class Model:
        config = SimpleNamespace(
            model_type=model_type,
            vision_config=SimpleNamespace(hidden_size=dimensions),
        )

        def to(self, device):
            assert device == "cpu"
            return self

        def eval(self):
            return self

    model = Model()

    class ProcessorLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["processor"] = (path, kwargs)
            return processor

    class ModelLoader:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls["model"] = (path, kwargs)
            return model

    torch = ModuleType("torch")
    torch.set_num_threads = lambda count: calls.update(threads=count)
    transformers = ModuleType("transformers")
    transformers.AutoImageProcessor = ProcessorLoader
    transformers.AutoModel = ModelLoader
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return calls, processor, model


def test_pinned_siglip2_fixed_resolution_checkpoint_loads(monkeypatch):
    calls, processor, model = checkpoint_modules(monkeypatch)
    embedder = SiglipEmbedder("/pinned/checkpoint")
    embedder.load()
    assert embedder.model is model
    assert embedder.processor is processor
    assert calls["processor"][1]["use_fast"] is False
    assert calls["model"][1]["local_files_only"] is True
    assert calls["model"][1]["trust_remote_code"] is False
    assert calls["model"][1]["use_safetensors"] is True
    embedder.load()
    assert calls["threads"] == 2


@pytest.mark.parametrize("model_type,dimensions", [("bert", 768), ("siglip", 512)])
def test_unexpected_architecture_or_dimensions_fail_closed(monkeypatch, model_type, dimensions):
    checkpoint_modules(monkeypatch, model_type, dimensions)
    with pytest.raises(HTTPException) as raised:
        SiglipEmbedder("/pinned/checkpoint").load()
    assert raised.value.status_code == 503
