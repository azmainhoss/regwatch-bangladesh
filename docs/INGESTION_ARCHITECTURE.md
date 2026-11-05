# Regulatory Document Ingestion Architecture
## RegWatch Bangladesh Platform

### 1. Ingestion Overview
The regulatory ingestion subsystem collects official publications issued by Bangladesh Bank (and future regulatory authorities).
Because financial regulation demands absolute legal certainty and evidentiary auditability, the ingestion engine treats all external assets as immutable evidence.

```
[ External Source: BB Web / Admin Dropzone ]
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
- **WAF / Anti-Bot Findings & Safe Architecture:**
  - Direct non-browser HTTP queries to `bb.org.bd` trigger an Imperva / TSPD anti-bot challenge.
  - In accordance with our security principles, the system **never attempts to bypass or solve anti-bot challenges**.
  - The ingestion architecture therefore operates with dual input pipelines:
    1. **Automated Source Connector:** Executes in network environments where whitelisting or public mirror feeds are available, with strict rate limiting (3-second delays between requests) and standard User-Agent identification.
    2. **Manual & Batch Document Dropzone:** Admin users, regulatory analysts, or batch ingestion scripts can upload official PDF files directly via the Admin Console, CLI tool, or `/api/v1/documents/upload` endpoint with complete provenance preservation.

---

### 3. Checksums, Immutability & Versioning
- **Identity Hash:** Every ingested document is hashed using SHA-256 over its raw byte stream before any processing.
- **Deduplication:**
  - If a file with an identical SHA-256 hash has already been ingested, the system marks the discovery as `EXISTING_HASH` and references the existing `document_version`.
  - If a document with the same `reference_number` or canonical URL is re-issued with different content (modified PDF), a new `document_version` is appended with incremented `version_number`. The prior version and its extracted pages are preserved unchanged.

---

### 4. Ingestion Lifecycle State Machine
1. `DISCOVERED`: Discovered via connector or uploaded.
2. `QUEUED`: Queued for extraction.
3. `DOWNLOADING`: Stream download in progress (for crawler).
4. `DOWNLOADED`: Stored in `originals/` storage namespace.
5. `EXTRACTING`: Page-level text extraction and OCR running.
6. `EXTRACTED`: Pages and raw text stored in `document_pages`.
7. `ANALYSIS_PENDING`: Queued for AI analysis.
8. `ANALYZING`: Multi-stage AI pipeline running.
9. `AWAITING_REVIEW`: Completed AI analysis flagged for human editor review.
10. `PUBLISHED_MACHINE_PROCESSED`: Published automatically if deterministic quality score >= threshold.
11. `PUBLISHED_HUMAN_REVIEWED`: Reviewed and approved by regulatory editor.
12. `FAILED`: Ingestion or extraction failed with error diagnostics recorded in `source_runs`.
