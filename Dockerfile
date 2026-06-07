# ── Stage 1: Node.js dependencies (JSONata runner) ───────────────────────────
FROM node:20-alpine AS node-deps
WORKDIR /scripts
COPY scripts/package.json ./
RUN npm ci --omit=dev

# ── Stage 2: Python build ────────────────────────────────────────────────────
FROM python:3.12-slim AS python-build
WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install Node.js runtime only
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Python packages
COPY --from=python-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-build /usr/local/bin /usr/local/bin

# Copy Node modules
COPY --from=node-deps /scripts/node_modules ./scripts/node_modules

# Copy application
COPY scripts/jsonata_runner.js ./scripts/
COPY app/ ./app/

# Security: non-root user
RUN useradd -m -u 1001 appuser && mkdir -p data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
