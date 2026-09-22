# Multi-stage build. The runtime image carries no build tools, no dev
# dependencies and no compiler, and runs as a user with no privileges.

# ---------------------------------------------------------------- build
FROM python:3.12.13-slim-bookworm AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Wheels for lxml and cffi need a compiler; it stays in this stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libffi-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------- runtime
FROM python:3.12.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

# WeasyPrint shapes text through Pango and HarfBuzz. The Noto fonts are what
# make Hindi and Marathi render correctly in an exported PDF rather than as
# boxes, so they are part of the runtime, not an optional extra.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libharfbuzz0b \
      libffi8 \
      fontconfig \
      fonts-noto-core \
      fonts-noto-ui-core \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin nyayalens

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=nyayalens:nyayalens app/ ./app/
COPY --chown=nyayalens:nyayalens frontend/ ./frontend/

USER nyayalens

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz').read()"

# --proxy-headers so per-IP rate limiting sees the real client behind Cloud Run.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
