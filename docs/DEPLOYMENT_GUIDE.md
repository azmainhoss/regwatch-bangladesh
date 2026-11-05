# Deployment Guide
## RegWatch Bangladesh Platform

### 1. Environments
- **Local Development:** macOS/Linux, virtual environment (`.venv`), SQLite or local PostgreSQL, local storage namespace (`./storage`), mock or API LLM providers.
- **Staging / Production:** Containerized deployment using Docker & Docker Compose or Kubernetes, PostgreSQL 16 with `pgvector`, Redis 7, private S3-compatible object storage (MinIO or AWS S3), production LLM keys (Gemini / Claude / OpenAI).

---

### 2. Docker Compose Infrastructure
The project includes a multi-service `docker-compose.yml`:
1. `db`: PostgreSQL 16 with `pgvector` extension.
2. `redis`: Redis 7 Alpine for job queuing and cache.
3. `backend`: FastAPI Python application running with Uvicorn.
4. `worker`: Asynchronous document processing and OCR worker.
5. `frontend`: Next.js 14+ application serving the web workspaces.

---

### 3. Environment Secrets Management
- All sensitive variables (`SECRET_KEY`, `DATABASE_URL`, `S3_SECRET_ACCESS_KEY`, `GEMINI_API_KEY`) are injected via environment variables.
- Never commit actual `.env` files into source control. Always refer to `.env.example`.
