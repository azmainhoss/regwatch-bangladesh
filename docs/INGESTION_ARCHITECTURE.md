# Regulatory Document Ingestion Architecture
## RegWatch Bangladesh Platform

### 1. Ingestion Overview
The regulatory ingestion subsystem collects official publications issued by Bangladesh Bank (and future regulatory authorities).
Because financial regulation demands absolute legal certainty and evidentiary auditability, the ingestion engine treats all external assets as immutable evidence.

```
[ External Source: BB Web (own checker) / Admin Upload (backup) ]
                   │
                   ▼
       [ Source Connector Interface ]
        ├── BaseConnector (Abstract)
        ├── BangladeshBankConnector (Web Crawler)
        └── ManualSubmissionConnector (Admin / API)
                   │
                   ▼
         [ Deduplication Gate ]
        ├── SHA-256 Checksum Calculation
        └── Reference Number & URL Matching
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
    [Duplicate]         [New / Changed]
  (Skip or Version)          │
                             ▼
              [ Immutable Object Storage ]
              storage/originals/{hash}.pdf
                             │
                             ▼
               [ Document Lifecycle State ]
                       DISCOVERED
                           ↓
                        QUEUED
                           ↓
                      EXTRACTING
```

---

### 2. Bangladesh Bank Source Specifics
- **Primary Domain:** `https://www.bb.org.bd`
- **Key Publication Sections:**
  - `en/index.php/mediaroom/circular`: Central circular listing portal.
  - Departmental paths:
    - BRPD (Banking Regulation and Policy Department) - Capital adequacy, asset classification, loan write-offs, mergers.
    - DOS (Department of Off-site Supervision) - Prudential limits, liquidity coverage, CAMELS ratings.
    - FEPD (Foreign Exchange Policy Department) - FX trade regulations, export-import financing.
    - PSD (Payment Systems Department) - MFS, RTGS, NPSB, card payment rules.
    - SFD (Sustainable Finance Department) - Green financing, ESG compliance.
- **How the app talks to the site (DECISIONS.md 1 and 2):**
  - The app's own checker queries `bb.org.bd` directly. It runs from Bangladesh (home-hosted for now).
  - It identifies itself honestly as `RegWatchBot/0.1`, never as a browser.
  - One request at a time, at least 15 s apart (`BB_REQUEST_INTERVAL_SECONDS`), across listing checks,
    PDF downloads and HEAD checks. The pace and lock live in the scheduler process (`SCHEDULER_ENABLED` on one process only).
  - New-circular check: `POST en/index.php/mediaroom/circular` with `from_date`, `to_date` (last 7 days, inclusive)
    and `search_circular=Search`. A full-list GET runs once a day as a double-check.
  - Schedule (Asia/Dhaka, inside `MONITOR_WINDOW_START`-`MONITOR_WINDOW_END`, default 10:00-18:00):
    every 10 min Sun-Thu, hourly Fri-Sat, full-list reconcile at `RECONCILE_TIME` (17:50), archive re-check weekly.
  - Each item is keyed by its PDF URL. Parsed table rows are compared, never raw HTML.
  - Every listing check has an outcome: `OK`, `CHALLENGE`, `NO_TABLE`, `HTTP_ERROR` or `NETWORK_ERROR`.
    Anything but `OK` makes the run `FAILED_RETRY`; it never counts as "nothing new".
    Repeated failures back off from 30 min up to 6 h.
  - The system **never attempts to bypass or solve bot checks**. A bot check page means "failed, try later".
  - A "Request Rejected" reply for one PDF marks that file `SKIPPED_REJECTED`; the next file carries on.
  - **Backup path:** admins can still upload official PDFs via the Admin Console or `/api/v1/documents/upload`
    with full provenance, for example while the site is down.

---

### 3. Checksums, Immutability & Versioning
- **Identity Hash:** Every ingested document is hashed using SHA-256 over its raw byte stream before any processing.
- **Deduplication:**
  - If a file with an identical SHA-256 hash has already been ingested, the system marks the discovery as `EXISTING_HASH` and references the existing `document_version`.
  - If a document with the same `reference_number` or canonical URL is re-issued with different content (modified PDF), a new `document_version` is appended with incremented `version_number`. The prior version and its extracted pages are preserved unchanged and marked `SUPERSEDED`.
- **Archive headers:** every downloaded file keeps its `source_url`, `etag`, `last_modified` and `fetched_at`
  (on `document_versions` and `source_discoveries`).
- **Weekly re-check:** a HEAD request per shared-library PDF (same pace and lock). A changed ETag or Last-Modified
  triggers a download; a different SHA-256 becomes a new version, the same SHA-256 only refreshes the headers.
  Private user uploads are never rechecked.

### Page reading (DECISIONS.md 6 and 10)
Each page is routed by the fonts and characters of its text layer (`extraction/page_router.py`), never by the site's language label:
- Clean English text layer: read with PyMuPDF (pinned below 2), method `TEXT_LAYER`, status `SUCCESS_NATIVE`, one box per line in `line_boxes`.
- Legacy ANSI Bangla fonts (SutonnyMJ, NikoshBAN, NokshiStandard and similar), broken Bangla, Bangla Unicode, or almost no text (scan): stored empty with status `PENDING_VISION`.
- A background job (`extraction/vision_jobs.py`, started where `SCHEDULER_ENABLED` or `VISION_WORKER_ENABLED` is on) renders each waiting page at 200 dpi and asks Gemini (`VISION_MODEL`) for an exact transcription with a box per line. One call at a time; 429/503 are retried with backoff. Success: `SUCCESS_VISION`. Without `GEMINI_API_KEY` the pages keep waiting; after `VISION_MAX_ATTEMPTS` failed jobs a page goes to `NEEDS_HUMAN_REVIEW`. No placeholder text is ever stored.
- The Bangla archive is read by hand through the Gemini app (`research/archive/READING_PROMPT.md`) and loaded with `backend/scripts/import_manual_reading.py` (method `MANUAL_SUBSCRIPTION_READING`, status `SUCCESS_VISION_MANUAL`).

### Language variants
An English and a Bangla file of the same circular are filed under one document as two versions with their own `language`. They are both `CURRENT` and never supersede each other: a new file only supersedes older versions with the same language and the same source URL. The archive re-check looks at every `CURRENT` version, so both variants are checked.

---

### 4. Ingestion Lifecycle State Machine
1. `DISCOVERED`: Discovered via connector or uploaded. Candidate record created in `source_discoveries`.
2. `VALIDATED`: Metadata validated, candidate link verified as PDF/HTML publication.
3. `RESTRICTED`: Bot check page on an approved download. Diagnostics recorded; the scheduled checker instead leaves the file queued and backs off.
   `SKIPPED_REJECTED`: the site answered "Request Rejected" for this one file; other files carry on.
4. `QUEUED`: Queued for extraction.
5. `DOWNLOADING`: Stream download in progress (for crawler).
6. `DOWNLOADED`: Stored in `originals/` storage namespace with SHA-256 verification.
7. `EXTRACTING`: Page-level text extraction running (text-layer pages now; image-read pages wait as `PENDING_VISION`).
8. `EXTRACTED`: Pages and raw text stored in `document_pages`.
9. `ANALYSIS_PENDING`: Queued for AI analysis.
10. `ANALYZING`: Multi-stage AI pipeline running.
11. `AWAITING_REVIEW`: Completed AI analysis flagged for human editor review.
12. `PUBLISHED_MACHINE_PROCESSED`: Published automatically if deterministic quality score >= threshold.
13. `PUBLISHED_HUMAN_REVIEWED`: Reviewed and approved by regulatory editor.
14. `FAILED`: Ingestion or extraction failed with error diagnostics recorded in `source_runs`.

---

### 5. Phase 2 Connector & Discovery Review Queue Implementation
In Phase 2, the source monitoring and connector infrastructure was implemented:
- **`BaseSourceConnector` (`backend/app/modules/sources/connector/base.py`)**: Abstract base class defining `discover_candidates()`, `download_candidate()`, and `detect_anti_bot_challenge()`.
- **`BangladeshBankConnector` (`backend/app/modules/sources/connector/bangladesh_bank.py`)**: Concrete crawler targeting Bangladesh Bank Media Room circular portals. Parses circular tables, extracts circular numbers, dates, titles, and download URLs.
- **Anti-Bot Telemetry**: Detects Imperva TSPD JavaScript challenge signatures (`bobcmn`, "What code is in the image?", support ID), Cloudflare challenges, and HTTP 429/403/503. Preserves diagnostics in `source_runs.access_restriction_details` without attempting to bypass.
- **`SourceMonitoringService` (`backend/app/modules/sources/service.py`)**: Orchestrates runs, handles SHA-256 deduplication, records candidates into `source_discoveries`, and provides `approve_and_ingest_discovery()` and `reject_discovery()` review queue operations.
- **Admin Review Queue**: Accessible via `GET /api/v1/sources/discoveries` and the Next.js Admin UI, allowing compliance officers to review candidates, inspect WAF alerts, and approve or reject discovered items.
