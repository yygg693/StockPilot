# --- Frontend build stage ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend-v2/package*.json ./
RUN npm ci --silent
COPY frontend-v2/ .
RUN npm run build

# --- Backend runtime ---
FROM python:3.12-slim AS backend-runtime
WORKDIR /app

COPY pyproject.toml .
COPY backend/ backend/
COPY config.yaml .
COPY scripts/ scripts/

# Install dependencies (non-editable, no source needed for deps)
RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p data/backups

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# --- Frontend runtime (nginx) ---
FROM nginx:alpine AS frontend-runtime
COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1
EXPOSE 80
