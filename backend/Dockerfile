# VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE: API, worker and migrations image.
# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system atlas && useradd --system --gid atlas --home /app atlas
# Install ONLY from the hash-pinned lock. The build fails if it is missing.
COPY backend/requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY backend/ ./
COPY VERSION /app/VERSION
RUN mkdir -p /var/lib/atlas/snapshots && chown -R atlas:atlas /var/lib/atlas
USER atlas
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "--factory", "app.main:app_factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
