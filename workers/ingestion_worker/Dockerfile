# Build context must be the REPO ROOT (not this directory).
# The worker imports from both `workers/` and `apps/api/app/`.
#
# Build with:
#   docker build -f workers/ingestion_worker/Dockerfile -t rag-worker .
# Or use docker-compose (which sets the context automatically).

FROM python:3.12-slim

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

# System dependencies for OCR (Tesseract) and PDF rendering (PyMuPDF needs libGL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install API dependencies first (lighter, cached layer)
COPY apps/api/requirements.txt /tmp/api-requirements.txt
RUN pip install --no-cache-dir --index-url "${TORCH_INDEX_URL}" torch
RUN pip install --no-cache-dir -r /tmp/api-requirements.txt

# Install worker dependencies
COPY workers/ingestion_worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/worker-requirements.txt

# Copy full source (worker needs both packages on PYTHONPATH)
COPY apps/api/app /workspace/app
COPY workers /workspace/workers

ENV PYTHONPATH=/workspace
CMD ["python", "-m", "workers.ingestion_worker.main"]
