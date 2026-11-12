# Research 4: hands-on test of local models on real circulars (2026-11-10)

All files are in D:\regwatch-model-test (scripts and results in work\, gold answers in work\gold.json, the 8 PDFs in pdfs\).

## Setup
- **Machine:** i5-1135G7 laptop, CPU only.
- **Ollama:** 0.40.15. JSON-schema output, temperature 0, num_ctx 16384, thinking off.
- **8 documents:**
  - English: FEPD-2 Circulars 11 and 10, FEPD-1 Circular Letter 16 (amends FE Circular 27), BRPD-1 Circular 17 (deadline).
  - Long: FEPD-1 Circular 34, 17 pages.
  - Bangla (Bijoy converted span by span with unicodeconverter): BRPD-1 Circular Letters 37 and 33, BRPD-1 Circular 18.
- **Gold answers:** 91 required obligations and 12 relationships. Every gold quote was checked word for word.
- **Quote check:** an exact match after NFC and whitespace normalization.

## Rules alone (regex, no model)
| Measure | Result |
|---|---|
| Metadata (type, department, reference, issue date, effective date) | 100% |
| Relationships | 12/12, types right |
| Obligation sentences: recall / precision | 96.7% / 71.6% |
| Obligation type | 96% |
| Deadlines | 8/13 |
| Owning department | 8/8 |
| Quotes | 100% word for word (copied by construction) |
| Time | 0.14 s for all 8 |

**Caveat:** the rules were written after reading these 8 docs. On 40 other circulars, reference number plus date was right for 26/40,
or 28/40 after small fixes. Most misses were PDFs with broken Unicode fonts.

## Models (8 docs, whole document in one prompt)
"Quote OK" means word for word and on the right page.
| Model | Time per doc | tok/s | RAM | JSON valid | Obligations recall / precision | Quote OK | Relationships | Deadlines | Metadata |
|---|---|---|---|---|---|---|---|---|---|
| granite4:350m (IBM) | 160 s | 11.2 | 1.7 GB | 75% | 2% / 25% | 10% | 33% | 0/13 | 25% |
| LFM2-1.2B-Extract (Liquid) | 176 s | 14.1 | 1.5 GB | 63% | 7% / 44% | 11% | 33% | 0/13 | 30% |
| granite4.2:3b (IBM) | 471 s | 3.5 | 4.6 GB | 100% | 24% / 96% | 46% | 8% | 2/13 | 80% |
| qwen3:4b | 593 s | 2.8 | 7.0 GB | 100% | 26% / 93% | 80% | 75% | 1/13 | 90% |
| **NuExtract3 Q4_K_M (NuMind)** | 372 s | 4.8 | 5.4 GB | 100% | **46% / 85%** | **92%** | **100%** | **8/13** | 85% |
| lfm2.5:8b (Liquid, mixture of experts) | 131 s | 9.1 (13-16 when the machine was quiet) | 5.4 GB | 100% | 13% / 57% | 29% | 25% | 0/13 | 78% |
| granite4.2:8b (IBM; partial, 2 docs) | 288 s | 3.1 | 8.2 GB | 100% | 5/5 | 86% | 2/2 | n/a | 100% |

**Not run:** gemma3:4b, granite4:3b, qwen3:1.7b, llama3.2:3b. Their files were deleted mid-test.
**Skipped:** phi4-mini and gemma3n (download limit); TigerLLM and titulm (no GGUF); ReaderLM-v2 (different job); SaulLM (too big, English only).
**Installed but not run:** GLiNER.

## Ways of asking the model
- **Span pointer:** the model gets numbered sentences and returns sentence IDs, and the code pulls the exact text.
  - Quote accuracy: qwen3 went from 80% to 92%, and lfm2.5 from 29% to 85%.
  - About 40% faster.
- **Hybrid:** the rules pick candidate sentences, and the model only labels them and writes the summary.
  - Recall 97%, precision 77%, quotes 100%.
  - But the model's labels were worse than the rules' own: type 70% vs 96%, deadlines 3/13 vs 8/13.
- **Long document (17 pages):**
  - Whole document in one prompt: qwen3 found 5/30 obligations in 821 s.
  - Page by page: it found 29/30 in 2,016 s, but precision fell to 65%.
  - Larger prompts slowed it sharply and pushed RAM from 3.2 GB to 7 GB.

## Bangla
- **qwen3:4b** was the only usable one for an English summary: about 70% of key facts, with real mistakes.
- **NuExtract3** quoted Bangla correctly and found every reference, but wrote its summaries in Bangla.
- **The rest** were weak or invented quotes.
- **Verdict:** no small local model handles Bangla well enough to trust.

## Tester's opinion
- **Rules do:** metadata, relationships, candidate obligation sentences, deadlines, owning department.
- **A small local model (NuExtract3 or qwen3:4b), only in hybrid or span-pointer mode,** could add an English summary and labels.
  That's 2-10 minutes per doc on a 4-8 GB CPU server. Quotes always come from code.
- **Needs an API or a GPU-hosted model:** reliable obligation typing, Bangla summaries, long documents at reasonable speed.

## Bot-check finding
- **Blocked** (HTTP 200 HTML challenge pages, 40-50 KB) at 01:25-01:28:
  curl with a browser-like User-Agent ("Mozilla/5.0 ... Chrome/130"), no other headers, 3 s apart.
- **Not blocked** at 01:31-01:32: the honest User-Agent "RegWatchBot/0.1", 10 s apart. All 7 PDFs came back.
- **Inference:** the fake browser identity triggered the check; the honest bot name did not.

## Side effects on this PC
- **A disk cleanup at about 01:20 wiped the scratchpad and the C: Ollama model files (about 9 GB).**
  The normal Ollama now lists no models. Copies of gemma3:4b, granite4:3b, qwen3:1.7b and llama3.2:3b are in D:\regwatch-model-test\ollama-models.
- **Left on C:** 16 tiny partial-download files in C:\Users\User\.ollama\models\blobs, plus a 680 KB venv remnant.
- **Ollama:** something restarted it at about 04:00. It now listens on 0.0.0.0 (reachable from the local network).
