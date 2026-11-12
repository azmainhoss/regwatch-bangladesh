# Deep research prompt (paste everything below the line into a chat with deep research on)

---

I'm building a regulatory monitoring SaaS for Bangladesh. It watches Bangladesh Bank (bb.org.bd) for new circulars, reads each PDF, and turns it into compliance intelligence for banks: a summary, the obligations (must / must not / may / report / keep records / get approval / disclose), who each rule applies to (commercial banks, Islamic banks, NBFIs, payment operators, MFIs, money changers), deadlines and effective dates, the document type and issuing department, and which older circulars it amends, repeals, supersedes or clarifies. Banks then turn the obligations into an internal to-do list with owners and evidence. The hard rule: every claim must quote the source text word for word and cite the page. Nothing unverifiable gets published.

The facts below come from my own checks:
- About 300 new circulars a year (22 to 45 a month in 2026), plus a one-time backlog of about 4,800 historical ones.
- Documents are in English, Bangla or both. Most are 1 to 10 pages. Some guidelines run 50 to 200 pages. Some old ones use the legacy Bijoy/SutonnyMJ font encoding, and some are scanned.
- The whole thing has to run on a small, cheap server (think 1 to 4 GB RAM, 1 to 2 vCPU, maybe no GPU), or close to it.

Please research and compare the options, with 2025 to 2026 sources wherever you can, and give a clear recommendation for each part:

1. **Document understanding without a big cloud AI API.** How far can deterministic and classical methods get on this task? Think regex and rule grammars for reference numbers, dates and "amends / in partial modification of / supersedes" phrases, dateparser/duckling, spaCy, CRF/NER, and small fine-tuned encoders such as BanglaBERT, XLM-R and mDeBERTa for obligation sentence classification and applicability tagging. Which sub-tasks need a generative model, if any? Summaries probably do. Do obligations?

2. **Small local LLMs (CPU-friendly, 2025 to 2026).** Consider Qwen3 and Qwen3.5 small sizes, Gemma 3 and Gemma 3n, Llama 3.x small, Phi-4-mini, SmolLM3, Granite 4, and Bangla-tuned models such as TigerLLM, BanglaLLaMA and titulm. For each, report:
   - Bangla quality
   - quality on legal and regulatory extraction
   - support for structured JSON output (llama.cpp grammars, Outlines, XGrammar)
   - RAM at Q4/Q5 quantization
   - tokens per second on a 2 to 4 vCPU box
   - license

   Include any benchmarks on legal or regulatory information extraction (LegalBench, LexGLUE, contract clause extraction, obligation extraction papers) and on Bangla (BanglaBench, Bangla MMLU and similar).

3. **Cheap hosted APIs as the alternative.** Compare Gemini Flash-Lite and Flash, Claude Haiku, the GPT mini/nano tiers, DeepSeek, Mistral Small and Qwen API, on:
   - per-token price
   - total yearly cost for my volume (estimate tokens per circular)
   - Bangla quality
   - structured output reliability
   - data-retention terms
   - batch discounts

   Also cover the per-job serverless GPU option (Modal, RunPod, Replicate) for running an open model only when a circular arrives.

4. **Grounding and verification.** What are the best current methods to force and check verbatim quotes with page citations? Consider extract-then-verify, span-pointer extraction instead of free text, constrained decoding over source spans, and fuzzy-match thresholds for Bangla text normalization (Unicode NFC, zero-width joiners, Bijoy conversion artifacts). How do production regtech and legal-tech products (CUBE, Regology, Corlytics, Compliance.ai, Harvey, Luminance) handle this?

5. **Relationship detection between circulars** (amends, repeals, supersedes, references). Cover citation-parsing approaches, how legal citation graphs are built (for example the EU's EUR-Lex/CELLAR, legislation.gov.uk, India's IndianKanoon), and whether ML adds anything beyond good rules for circulars that explicitly name earlier circular numbers.

6. **Applicability and routing.** Turning "applies to all scheduled banks / Islamic banks / NBFIs" into tags, and suggesting which internal bank department (Credit, AML, Treasury, IT, Ops) should own an obligation. Compare keyword taxonomies, zero-shot classifiers, embedding similarity, and small fine-tuned classifiers. Also cover how to bootstrap training labels cheaply, for example labelling once with a strong model, then distilling into a small one.

7. **The final recommendation.** Give a concrete hybrid design for my volume. Say which sub-task uses rules, a small classifier, a local LLM or an API, and give the expected RAM, CPU, latency per circular and monthly cost. Then say plainly whether running a local model is worth it at about 300 documents a year, compared with a cheap API plus strict quote verification.

Please cite sources for every number. Mark anything you could not verify.
