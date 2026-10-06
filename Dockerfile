FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

RUN pip install --no-cache-dir uv==0.12.22

WORKDIR /app

# As dependências primeiro, para o cache da camada sobreviver a mudança de código.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin eventos \
    && mkdir /data \
    && chown 10001:10001 /data

# O commit que o /healthz devolve. O deploy passa: --build-arg EVENTOS_COMMIT=<sha>.
ARG EVENTOS_COMMIT=desconhecido
ENV EVENTOS_COMMIT=${EVENTOS_COMMIT} \
    EVENTOS_DB=/data/eventos.sqlite \
    EVENTOS_HOST=0.0.0.0 \
    EVENTOS_PORT=8000 \
    PATH="/app/.venv/bin:${PATH}"

USER 10001
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

CMD ["python", "-m", "eventos", "servir"]
