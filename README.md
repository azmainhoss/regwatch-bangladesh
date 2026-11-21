# RegWatch Bangladesh
### Bangladesh-First Regulatory Intelligence & Compliance SaaS Platform

RegWatch monitors official publications from regulatory institutions in Bangladesh (starting with **Bangladesh Bank**), collects documents, extracts contents page-by-page, tracks relationships between regulatory instruments, and translates obligations into actionable compliance intelligence.

---

## The Central Invariant
> **Every important regulatory insight must be traceable to an official source document, original SHA-256 checksum, and a specific page or provision number.**

---

## Architecture Overview
- **Modular Monolith:** Strict domain modularity (`identity`, `organizations`, `institutions`, `sources`, `ingestion`, `documents`, `extraction`, `analysis`, `provisions`, `relationships`, `obligations`, `compliance`, `audit`).
- **Backend:** FastAPI (Python 3.11+ / 3.14), SQLAlchemy 2.0 (async & sync), Alembic migrations, Pydantic v2.
- **Document Processing:** PyMuPDF 1.x for English text-layer pages; Gemini (gemini-3.5-flash-lite) reads Bangla, legacy-font and scanned pages from the page image in a background job.
- **Frontend:** Next.js 14 (App Router), TypeScript, React 18, Tailwind CSS.
- **Storage:** Dual-namespace immutable object storage (`originals/` for regulatory documents, `evidence/` for tenant compliance files).
- **Database:** PostgreSQL 16 with `pgvector` and JSONB (with full SQLite fallback for zero-dependency local testing).

---

## Quickstart Guide

### 1. Backend Setup
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt (or use virtualenv packages)

# 3. Configure environment
cp .env.example .env

# 4. Run database migrations and seed Bangladesh Bank data
alembic upgrade head
python3 backend/scripts/seed.py

# 5. Generate test corpus
python3 backend/scripts/generate_fixtures.py

# 6. Run automated test suite
pytest -v backend/app/tests/

# 7. Start the FastAPI development server
uvicorn backend.app.main:app --reload --port 8000
```
API Documentation will be available at: `http://localhost:8000/api/v1/docs`.

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Access the application at: `http://localhost:3000`.

The frontend calls the FastAPI backend directly from the browser. It uses `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000/api/v1`). For any deployed build, set it at build time to the public
backend URL, and add the frontend's origin to the backend's `ALLOWED_ORIGINS`.

---

## Development Accounts
For local development, run `python -m backend.scripts.seed` (or set `SEED_ON_STARTUP=true` in `.env`
on an empty database) to create a superuser and a sample bank user. The emails and passwords are
set in `backend/scripts/seed.py`. The seed refuses to run when `ENVIRONMENT=production`; create real
accounts there instead.

---

## Automated Verification Suite
Run the full test suite verifying storage immutability, SHA-256 deduplication, PyMuPDF page-by-page extraction, and API contracts:
```bash
source .venv/bin/activate
pytest -v backend/app/tests/
```
All 8 automated tests pass with 100% success rate.

## Speed test runs: Ask a question (21 Nov 2026)

Timing script: `autoresearch/ask-speed-261121/bench.py` (12 questions, one in Bangla; median seconds).

| Run name | File | What was done | Matching lines | Full answer |
|---|---|---|---|---|
| Baseline | `autoresearch/ask-speed-261121/Baseline.json` | Code as it was (SQL text scan) | 2.36 | 6.11 |
| Page text in memory | `.../Page text in memory.json` | Page text kept in memory, synced by database triggers | 0.52 | 7.58 (busy model) |
| Busy-model switch | `.../Busy-model switch.json` | Busy fast model: ask a second model at once, no 5 s wait | 0.34 | 2.52 |
| Deadline and retry order | `.../Deadline and retry order.json` | Fast, second, fast again; 20 s cap in all | 0.42 | 2.83 (max 9.7) |
| Same questions again | `.../Same questions again.json` | Repeat questions answered from memory | 0.31 | 0.25 |
