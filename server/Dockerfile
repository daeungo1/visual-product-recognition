FROM python:3.11-slim-bookworm AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/ \
    HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install the CPU wheel first; its local version satisfies torch==2.8.0.
RUN pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[cloud,inference]"
RUN pip check && python -c "import torch; assert torch.version.cuda is None, 'CPU Torch required'"
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download( \
    repo_id='google/siglip2-base-patch16-224', \
    revision='75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2', \
    local_dir='/opt/models/siglip2-base-patch16-224', \
    allow_patterns=['config.json', 'preprocessor_config.json', '*.safetensors'])"
COPY runtime_bootstrap/assets/demo-target.png /tmp/model-smoke.png
RUN HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -c "import math; from pathlib import Path; from guide_api.azure_adapters import SiglipEmbedder; from guide_api.images import image_bytes; \
    vector = SiglipEmbedder('/opt/models/siglip2-base-patch16-224').embed( \
    image_bytes(Path('/tmp/model-smoke.png').read_bytes())); \
    assert len(vector) == 768 and all(math.isfinite(value) for value in vector); \
    assert math.isclose(sum(value * value for value in vector), 1.0, abs_tol=1e-5); \
    print('Pinned CPU SigLIP2 smoke: 768 finite normalized features')"

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home app \
    && mkdir -p /app/data /app/runtime \
    && chown -R 10001:10001 /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models
COPY runtime_bootstrap/assets/demo-target.png /app/assets/demo-target.png
COPY runtime_bootstrap/assets/panel_map.json /app/assets/panel_map.json
COPY runtime_bootstrap/pipeline/provision_cloud.py /app/pipeline/provision_cloud.py
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app/runtime \
    TMPDIR=/app/runtime \
    HF_HOME=/app/runtime/huggingface \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    EMBEDDING_MODEL_PATH=/opt/models/siglip2-base-patch16-224 \
    VISUAL_GUIDE_MODE=cloud \
    PORT=8000
WORKDIR /app
USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn guide_api.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --limit-concurrency 32 --timeout-keep-alive 5"]
