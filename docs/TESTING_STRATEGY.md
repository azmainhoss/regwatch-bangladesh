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

#### 2.3 Automated Test Execution
- Run using `pytest -v` with coverage metrics.
