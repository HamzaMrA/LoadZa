# Two stages: build the viewer with Node, serve it and the API from Python.
# One image, one port, no reverse proxy to configure -- the whole point of the
# viewer's relative asset paths is that it can be served from the API's origin.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LOADZA_DB=/data/loadza.sqlite

COPY pyproject.toml README.md ./
COPY core/ core/
COPY app/ app/
COPY tools/ tools/
COPY bench/ bench/
RUN pip install --no-cache-dir -e ".[viz,api]"

COPY data/demo/ data/demo/
COPY --from=web /web/dist/ /app/web-dist/

# The database lives on a volume; a container that loses every job it ever
# solved when it restarts is a demo, not a service.
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
