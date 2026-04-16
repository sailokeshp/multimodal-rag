# Implementation Progress

## Phase 1 — Local MVP

### Status: COMPLETE ✓

---

## What is implemented and working

### FastAPI (`apps/api/`)
- [x] `config.py` — all env vars, model name/dim config, API key, score threshold
- [x] `db/models.py` — files, document_chunks, images, search_logs with pgvector
  - TEXT_EMBED_DIM=384 (matches BAAI/bge-small-en-v1.5 default)
  - IMAGE_EMBED_DIM=1152 (matches SigLIP2 so400m)
- [x] `db/session.py` — async SQLAlchemy
- [x] `db/migrations/create_tables.py` — one-shot migration runner
- [x] `routes/upload.py` — presigned PUT URL, complete-upload, `POST /upload/local` for dev
- [x] `routes/status.py`, `routes/search.py`, `routes/answer.py`
- [x] `services/storage_service.py` — S3 / local FS abstraction
- [x] `services/ingestion_service.py` — SQS enqueue or inline (local)
- [x] `services/retrieval_service.py` — text vector + image vector + PG FTS + merge/rerank
  - `run_in_executor` for CPU-bound embedding calls (event loop safe)
  - score thresholding (RETRIEVAL_SCORE_THRESHOLD)
  - query-type-aware weight adjustment
  - deduplication by snippet prefix / imageId
- [x] `services/answer_service.py` — grounded QA with deduplication + citation append
- [x] `prompts/grounded_answer.py` — grounded answer, page summary, caption, classify prompts
- [x] `utils/security.py` — optional API key middleware
- [x] `main.py` — CORS, lifespan, API key dependency

### Ingestion Worker (`workers/ingestion_worker/`)
- [x] `parsers/pdf_parser.py` — PyMuPDF, per-page OCR flag, inline image extraction
- [x] `parsers/docx_parser.py` — python-docx blocks + zip image extraction
- [x] `parsers/image_parser.py` — thumbnail + text heuristic
- [x] `ocr/tesseract_ocr.py`, `ocr/textract_adapter.py`
- [x] `chunking/text_chunker.py` — heading-aware, overlapping, 400-800 token target
- [x] `chunking/page_summary.py` — Gemma summaries with truncation fallback (no circular import)
- [x] `embeddings/siglip2_shared.py` — shared SigLIP2 model singleton (loaded once)
- [x] `embeddings/embedding_gemma.py` — REAL sentence-transformers (BAAI/bge-small-en-v1.5)
  - dim validation at load time
  - BGE query prefix for search queries
  - thread-safe singleton
- [x] `embeddings/siglip2_image.py` — REAL SigLIP2 image encoder (L2 normalised)
- [x] `embeddings/siglip2_text.py` — REAL SigLIP2 text encoder (same model space)
- [x] `embeddings/gemma_gen.py` — REAL generation with two backends:
  - `google_ai`: google-genai SDK (free Gemini API, recommended)
  - `local`: HuggingFace pipeline (configurable model)
- [x] `pipeline/ingest_file.py` — full pipeline, fixed:
  - deferred imports (no circular at startup)
  - checksum + size recording
  - READY skip (idempotency)
  - per-page flush
  - isolated error handling per step

### Infrastructure
- [x] `docker-compose.yml` — Postgres/pgvector + API + worker, build context fixed to repo root
- [x] Worker Dockerfile — fixed: copies both `app/` and `workers/` packages
- [x] `infra/scripts/init_db.sql`
- [x] `.env.example` — complete with all vars and documentation
- [x] `Makefile` — setup, install, db-up/down, migrate, api, worker, test, local-upload, local-search
- [x] `README.md` — full setup, model config, API reference, troubleshooting

### Tests (50/50 passing)
- [x] `tests/unit/test_chunker.py` — 10 tests
- [x] `tests/unit/test_parsers.py` — 13 tests (PDF, DOCX, image, OCR)
- [x] `tests/unit/test_schemas.py` — 9 tests
- [x] `tests/unit/test_embeddings.py` — 8 tests (mocked — no model download)
- [x] `tests/unit/test_retrieval_merge.py` — 10 tests (merge, rerank, classify)
- [x] `tests/conftest.py` — PYTHONPATH and env setup

### Evaluation
- [x] `scripts/eval_retrieval.py` — Recall@K, MRR, latency reporting

---

## How to run locally

```bash
# First time
make setup        # creates venv, installs deps, starts postgres, creates tables

# Daily
make api          # start API at :8000
make local-upload FILE=my.pdf
make local-search Q="your query"

# Tests
make test
```

---

## Remaining / Phase 2+

### Short-term
- [ ] Install SigLIP2 deps (`make install-ml`) and verify image embedding end-to-end
- [ ] Create a gold eval dataset from real uploaded documents
- [ ] Add `POST /upload/local` multipart support in the web frontend

### Phase 2 — AWS
- [ ] RDS Postgres with pgvector
- [ ] S3 presigned upload flow (routes/upload.py `request` and `complete` endpoints)
- [ ] SQS worker (set SQS_QUEUE_URL)
- [ ] Lambda/ECS API deployment
- [ ] Terraform infra scaffolding

### Phase 3 — Quality
- [ ] Gemma-based query classifier (replace heuristic in retrieval_service.py)
- [ ] BM25 lexical fallback (OpenSearch or pg_bm25)
- [ ] Reranker model (cross-encoder or Gemma scoring)
- [ ] Frontend (React/Next.js)
- [ ] Multi-tenant auth + row-level security

---

## Model configuration quick reference

| Role | Default model | Dim | Install |
|---|---|---|---|
| Text embeddings | BAAI/bge-small-en-v1.5 | 384 | `make install` |
| Image embeddings | google/siglip2-so400m-patch16-384 | 1152 | `make install-ml` |
| Generation | Gemini 2.0 Flash (Google AI) | — | free API key |
| Generation (local) | google/gemma-2-2b-it | — | `make install-ml` |
