# Testing Strategy & Quality Assurance
## RegWatch Bangladesh Platform

### 1. Testing Philosophy
In financial and regulatory technology, software bugs lead to non-compliance, regulatory penalties, and reputational risk. The platform maintains a zero-tolerance policy for fabricated test results or untested assertions.

---

### 2. Test Pyramid & Coverage Requirements

#### 2.1 Backend Unit & Integration Tests (`pytest`)
- **Core Models & Database Integrity:**
  - Foreign key constraints, unique constraints, and cascade rules.
  - UUID generation and timestamp behavior.
- **Deduplication & Storage:**
  - SHA-256 calculation idempotency.
  - Version increment logic on modified documents.
- **Extraction Engine Tests:**
  - Text extraction from clean native PDFs.
  - OCR extraction on scanned images.
  - Detection of Bangla vs English text.
  - Page-level segmentation and metadata persistence.
- **AI Schema & Validation Tests:**
  - Pydantic schema validation on structured AI outputs.
  - Citation verification engine (accurate calculation of quote coverage).
- **Tenant Isolation Tests:**
  - Verify that User from Org A cannot read or mutate compliance registers, items, tasks, or evidence belonging to Org B.
- **Publication Lifecycle Tests:**
  - Valid transitions through the state machine (`DISCOVERED` -> `PUBLISHED_HUMAN_REVIEWED`).

#### 2.2 Golden Test Corpus (Real Bangladesh Bank Documents)
- Maintained under `backend/app/tests/fixtures/corpus/`.
- Contains genuine representative publications:
  1. `bb_brpd_2024_15.pdf`: BRPD Circular 15/2024 (Loan Classification & Provisioning under IFRS 9).
  2. `bb_brpd_2024_16.pdf`: BRPD Circular 16/2024 (Ultimate Beneficial Ownership Disclosure).
  3. `bb_dos_2024_01.pdf`: DOS Circular 01/2024 (Off-site Supervision).
- Every test suite evaluates extraction accuracy, obligation capture, and relationship citation against these verified ground-truth documents.

#### 2.3 Automated Test Suite Execution
The backend maintains a comprehensive automated test suite with 20 tests across 8 test modules:
1. `test_auth_api.py`: Health endpoints, user registration, JWT generation, authenticated me queries.
2. `test_institutions_sources_api.py`: Institutions listing, departments lookup, source discovery.
3. `test_documents_ingestion_api.py`: Unauthenticated upload rejection (401), fake PDF magic byte rejection (422), authenticated ingestion, SHA-256 deduplication, page extraction, and PDF streaming.
4. `test_extraction.py`: Native text extraction on test corpus, Bijoy/ANSI font detection.
5. `test_storage.py`: Storage immutability, SHA-256 calculation, and path traversal block.
6. `test_security_boundaries.py`: Minimum password length validation, expired JWT rejection, tampered JWT signature rejection, and `/etc/shadow` path traversal block.
7. `test_multi_tenant_security.py`: Comprehensive Org A vs Org B cross-tenant register access, task creation, evidence upload, evidence inspection, raw file download, and URL ID substitution attacks all blocked with 403/404.
8. `test_phase2_source_monitoring.py` & `test_advanced_ingestion_and_jobs.py`: HTML table parsing, Imperva anti-bot detection, crawler runs with discovery queueing, review queue approvals/rejections, source activation toggles, date parser edge cases, unauthorized crawler triggers, and corrupt PDF rejections.

Execute test suite:
```bash
source .venv/bin/activate
pytest -v backend/app/tests/
```
All 20 tests pass cleanly without errors.
