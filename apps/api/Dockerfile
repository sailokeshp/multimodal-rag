# Build context is the REPO ROOT.
# docker build -f apps/api/Dockerfile -t rag-api .

FROM python:3.12-slim

WORKDIR /app

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir --index-url "${TORCH_INDEX_URL}" torch
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./app
COPY workers ./workers

ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
