"""
Gold Benchmark Regulatory Corpus Manifest for RegWatch Bangladesh.
Strictly records the provenance, synthetic vs authentic status,
expected ground truth, and known extraction limitations.
"""

from typing import Any, Dict, List

GOLD_CORPUS_MANIFEST: List[Dict[str, Any]] = [
    {
        "filename": "gold_en_digital_master_policy.pdf",
        "provenance_type": "SYNTHETIC_BENCHMARK",
        "authority": "Bangladesh Bank",
        "department": "BRPD",
        "reference_number": "BRPD Circular No. 15",
        "publication_date": "2024-11-27",
        "page_count": 2,
        "language": "en",
        "category": "ENGLISH_NATIVE_DIGITAL",
        "expected_clauses": ["1.", "1.1", "1.2", "1.3", "2.", "3."],
        "expected_tables_count": 1,
        "expected_table_keywords": ["Standard", "Special Mention", "Sub-Standard", "Doubtful", "Bad or Loss"],
        "known_limitations": "Text-aligned ASCII rule table format rather than embedded vector PDF lines."
    },
    {
        "filename": "gold_legacy_bijoy.pdf",
        "provenance_type": "SYNTHETIC_BENCHMARK",
        "authority": "Bangladesh Bank",
        "department": "BRPD",
        "reference_number": "04/2014",
        "publication_date": "2014-04-15",
        "page_count": 1,
        "language": "bn",
        "category": "LEGACY_BIJOY_ANSI",
        "expected_clauses": ["1.", "2."],
        "expected_tables_count": 0,
        "expected_converted_keywords": ["বাংলাদেশ ব্যাংক", "ঋণ শ্রেণিকরণ", "কার্যকর"],
        "known_limitations": "Requires Bijoy-to-Unicode conversion; raw text appears as ASCII glyphs."
    },
    {
        "filename": "gold_scanned_english.pdf",
        "provenance_type": "SYNTHETIC_BENCHMARK",
        "authority": "Bangladesh Bank",
        "department": "DOS",
        "reference_number": "DOS Circular No. 02/2024",
        "publication_date": "2024-01-15",
        "page_count": 1,
        "language": "en",
        "category": "SCANNED_ENGLISH_OCR",
        "expected_clauses": ["1.", "2.", "3."],
        "expected_tables_count": 0,
        "expected_ocr_keywords": ["BANGLADESH BANK", "Cash Reserve Ratio", "Statutory Liquidity Ratio"],
        "known_limitations": "Scanned bitmap image with 0 native character streams. Requires Tesseract OCR."
    },
    {
        "filename": "gold_scanned_bangla.pdf",
        "provenance_type": "SYNTHETIC_BENCHMARK",
        "authority": "Bangladesh Bank",
        "department": "BRPD",
        "reference_number": "০৮/২০২৪",
        "publication_date": "2024-08-01",
        "page_count": 1,
        "language": "bn",
        "category": "SCANNED_BANGLA_OCR",
        "expected_clauses": ["১.", "২."],
        "expected_tables_count": 0,
        "expected_ocr_keywords": ["বাংলাদেশ ব্যাংক", "গ্রিন ফাইন্যান্স"],
        "known_limitations": "Bitmap image rendered with macOS Bangla Sangam font; requires Tesseract Bengali OCR ('ben')."
    },
    {
        "filename": "gold_table_heavy_capital.pdf",
        "provenance_type": "SYNTHETIC_BENCHMARK",
        "authority": "Bangladesh Bank",
        "department": "DBI / BRPD",
        "reference_number": "BASEL-III-2024",
        "publication_date": "2024-06-30",
        "page_count": 1,
        "language": "en",
        "category": "TABLE_HEAVY_REGULATORY",
        "expected_clauses": [],
        "expected_tables_count": 2,
        "expected_table_keywords": ["Common Equity Tier 1", "Capital Conservation Buffer", "Dividend Restriction"],
        "known_limitations": "Multiple dense financial ratio tables on a single page."
    }
]
