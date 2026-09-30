# Audit UI (web/): Vite build, served by the API at "/"
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODEL_BACKEND=rules
WORKDIR /app
COPY dataset/requirements.txt dataset/requirements.txt
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
# Source set (api, dataset/collect, analysis, signals, monitor, benchmark,
# governance, train/common.py) is controlled by the .dockerignore allowlist.
COPY . .
COPY --from=web /web/dist web/dist
RUN useradd --create-home --uid 10001 app \
 && mkdir -p monitor/data governance/data && chown app monitor/data governance/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4)"
CMD ["uvicorn", "main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
