FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (includes: psutil, pymysql, ollama, matplotlib, numpy)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy core Python modules
COPY server.py .
COPY shell.py .
COPY myanos.py .
COPY myan_pm.py .
COPY build_packages.py .
COPY start.sh .
COPY ai_llm.py .
COPY code_executor.py .
COPY db_tidb.py .
COPY .mmr_history .

# Copy directories
COPY desktop/ desktop/
COPY terminal/ terminal/
COPY toolbox/ toolbox/
COPY myanai/ myanai/
COPY display_engine/ display_engine/
COPY ps2_layer/ ps2_layer/
COPY android_layer/ android_layer/
COPY packages/ packages/

# Build .myan packages into dist/
RUN python3 build_packages.py || echo "[WARN] Package build had warnings (non-fatal)"

# Ensure dist/ exists for runtime package management
RUN mkdir -p dist

EXPOSE 7860

ENV PORT=7860
ENV HOST=0.0.0.0

# Health check — verify server is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:7860/api/health || exit 1

CMD ["python3", "server.py", "7860"]
