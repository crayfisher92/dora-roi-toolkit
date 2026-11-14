# syntax=docker/dockerfile:1
# DORA RoI Workbench – local, single-user container.
#   docker compose up --build    → http://127.0.0.1:8000
#   docker run --rm -p 127.0.0.1:8000:8000 dora-roi-toolkit
# Behind a TLS-inspecting corporate proxy, pass its CA bundle as an (optional) build secret:
#   docker build --secret id=ca_bundle,src=/path/to/corporate-ca.pem -t dora-roi-toolkit .
FROM python:3.12-slim AS build
WORKDIR /src
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    pip wheel --wheel-dir /wheels ".[web,pdf]"

FROM python:3.12-slim
LABEL org.opencontainers.image.title="DORA RoI Workbench" \
      org.opencontainers.image.description="Validate, fix and analyse a DORA Register of Information" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/crayfisher92/dora-roi-toolkit"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 XDG_CACHE_HOME=/tmp/.cache
# Pango/HarfBuzz and a font for PDF reports (WeasyPrint); nothing else from apt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 \
       libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels \
    && useradd --create-home --uid 10001 roi
USER roi
WORKDIR /home/roi
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"
# Binds to all interfaces *inside* the container; publish only on localhost (see compose file).
CMD ["roi", "serve", "--host", "0.0.0.0", "--port", "8000"]
