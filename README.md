# Multimodal RAG

Semantic search over uploaded images, PDFs, and Word documents.

Upload files → search with natural language → get ranked results with source citations and optional grounded answers.

---

## What it does

- Upload **PDF**, **DOCX**, **JPG/PNG/WEBP**
- Automatically parses, OCRs (when needed), chunks, and embeds content
- **Text retrieval** via dense vector search (BGE embeddings)
- **Image retrieval** via cross-modal vector search (SigLIP2)
- **Hybrid retrieval**: vector + full-text, merged and reranked
- **Grounded answer generation** via Gemini API or local Gemma

---

## Architecture

```
Upload → S3/local → SQS/inline → Ingestion Worker
                                   ├─ PDF Parser (PyMuPDF)
                                   ├─ DOCX Parser (python-docx)
                                   ├─ Image Parser (Pillow)
                                   ├─ OCR (Tesseract, optional Textract)
                                   ├─ Chunker (structure-aware, overlapping)
                                   ├─ Text Embeddings (BGE via sentence-transformers)
                                   └─ Image Embeddings (SigLIP2)
                                            ↓
                                   PostgreSQL + pgvector
                                            ↑
FastAPI API ──── Search ─────────── Hybrid Retrieval
              └─ Answer ─────────── Gemini / local Gemma
```

---

## Quick start (local)

### Prerequisites

- Python 3.11+ (3.13 tested)
- Docker (for Postgres)
- Tesseract (for OCR): `brew install tesseract`
- A free Google AI Studio API key for answer generation: <https://aistudio.google.com/app/apikey>

### 1. Clone and set up

```bash
git clone <repo>
cd multimodal-rag

# Create venv and install dependencies
make install

# Configure environment
cp .env.example .env
# Edit .env — at minimum set GOOGLE_AI_API_KEY
```

### 2. Start Postgres

```bash
make db-up
```

### 3. Create database tables

```bash
make migrate
```

### 4. Start the API

```bash
make api
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### 5. Upload a file

```bash
# Via Makefile helper:
make local-upload FILE=path/to/your.pdf

# Or with curl:
curl -X POST http://localhost:8000/upload/local \
     -F "file=@path/to/your.pdf"
```

### 6. Search

```bash
make local-search Q="what is the termination notice period"

# Or with curl:
curl -X POST http://localhost:8000/search \
     -H "Content-Type: application/json" \
     -d '{"query": "termination notice period", "topK": 5, "includeAnswer": true}'
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload/local` | Direct multipart upload (local dev) |
| `POST` | `/upload/request` | Get presigned S3 PUT URL |
| `POST` | `/upload/complete` | Mark upload done, trigger ingestion |
| `GET` | `/files/{id}/status` | Poll ingestion status |
| `POST` | `/search` | Hybrid semantic search |
| `POST` | `/answer` | Generate grounded answer from provided context |
| `GET` | `/health` | Health check |

Full schema: `http://localhost:8000/docs`

---

## Model configuration

### Text embeddings

Set via `TEXT_EMBED_MODEL_NAME` + `TEXT_EMBED_DIM`.

| Model | Dim | Speed | Quality |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` (default) | 384 | Fastest | Good |
| `BAAI/bge-base-en-v1.5` | 768 | Fast | Better |
| `BAAI/bge-large-en-v1.5` | 1024 | Moderate | Best |

> **Important:** Changing the model requires recreating the Postgres tables (`make db-down db-up migrate`).

### Image embeddings (SigLIP2)

Requires `transformers` and `torch`:

```bash
make install-ml
```

Set `IMAGE_EMBED_MODEL_NAME=google/siglip2-so400m-patch16-384` (default, dim=1152).

SigLIP2 requires ~2 GB RAM. It runs on CPU but is slow. A machine with ≥8 GB RAM is recommended.

### Answer generation

**Option 1 (recommended): Google AI Studio — free, no GPU**

```env
GEN_MODEL_BACKEND=google_ai
GOOGLE_AI_API_KEY=your_key_here
GOOGLE_AI_MODEL=gemini-2.0-flash
```

**Option 2: Local HuggingFace model**

```env
GEN_MODEL_BACKEND=local
GEN_MODEL_NAME=google/gemma-2-2b-it
```

Requires: `make install-ml`. Gemma-2-2b-it needs ~4.5 GB RAM; GPU strongly recommended.

---

## Running tests

```bash
# Unit tests (no DB or network required):
make test

# All tests including integration (requires Postgres):
make test-integration
```

---

## Docker (full stack)

```bash
# Edit .env first
docker compose up --build
```

Services: `postgres`, `api` (port 8000), `worker`.

---

## Environment variables

See [.env.example](.env.example) for the full list with descriptions.

---

## Project layout

```
apps/api/           FastAPI application
workers/
  ingestion_worker/ Ingestion pipeline (parsers, embeddings, chunking)
infra/              Docker, Terraform stubs
tests/              pytest test suite
scripts/            Dev utilities
docs/               Progress notes, API contracts
```

---

## Deployment (AWS)

For AWS deployment:

1. Use RDS PostgreSQL with pgvector extension enabled
2. Use S3 for file storage (set `S3_BUCKET`, `AWS_*` credentials)
3. Use SQS for the ingestion queue (set `SQS_QUEUE_URL`)
4. Run the worker on ECS Fargate or EC2 (on-demand to control cost)
5. Run the API on Lambda + API Gateway or ECS

> AWS free-trial note: avoid always-on GPU endpoints. Use `GEN_MODEL_BACKEND=google_ai` for generation.

## GitHub Actions

This repo now supports a simple GitHub Actions CI/CD setup:

- `CI` runs on pull requests and pushes to `main`
- `Deploy to EC2` runs automatically after `CI` succeeds for a push to `main`
- `Deploy to EC2` can also be started manually from the Actions tab

The deploy workflow uses the existing EC2 deployment model in `infra/aws/deploy.sh`, so local deploys and GitHub deploys follow the same path.

Required GitHub repository secrets:

- `EC2_HOST`
- `EC2_SSH_KEY`
- `POSTGRES_PASSWORD`
- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `S3_BUCKET`
- `SQS_QUEUE_URL`
- `GROQ_API_KEY`

Optional GitHub repository secrets:

- `GOOGLE_AI_API_KEY`

Notes:

- `infra/aws/provision.sh` already updates `EC2_HOST`, `S3_BUCKET`, and `SQS_QUEUE_URL` automatically when the GitHub CLI is authenticated.
- The production workflow deploys the lightweight EC2-safe settings we verified in AWS: text/image embeddings disabled, S3 + SQS enabled, and Groq answer generation using `llama-3.1-8b-instant`.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'app'`**
→ Run with `PYTHONPATH=.:apps/api` prefix, or use the Makefile targets.

**`asyncpg.exceptions.InvalidPasswordError`**
→ Check `POSTGRES_*` vars in `.env` match your Postgres container config.

**Tesseract not found**
→ `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Linux). Set `USE_LOCAL_OCR=false` to skip.

**SigLIP2 load fails / out of memory**
→ `make install-ml` first. If OOM, disable image retrieval temporarily by not uploading images.

**Gemma generation returns stub message**
→ Set `GOOGLE_AI_API_KEY` in `.env` or install local model deps with `make install-ml`.
