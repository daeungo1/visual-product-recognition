FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv==0.9.27 \
    && uv sync --frozen --no-dev --no-install-project

COPY src ./src

RUN PYTHONPATH=/app/src python -m visual_guide.manual_staging \
    --destination /app/data/WD80H25BHS_OID139796_KO.pdf

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "visual_guide.main:app", "--host", "0.0.0.0", "--port", "8000"]
