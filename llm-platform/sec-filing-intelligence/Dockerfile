# ---------------------------------------------------------------- web build
FROM node:22-slim AS web

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY web/ ./
RUN npm run build


# --------------------------------------------------------------- wheel build
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip build && python -m build --wheel --outdir /dist


# ------------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

# Run as a non-root user; nothing here needs privileges.
RUN useradd --create-home --uid 10001 app
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=builder /dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# The API serves the built UI from this path when it is present, so the image
# is the whole app rather than an API that needs a separate static host.
COPY --from=web /web/dist /app/web/dist

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "filing_intel.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
