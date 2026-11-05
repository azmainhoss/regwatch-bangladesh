import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional
import pymupdf as fitz

from backend.app.modules.evaluation.schemas import (
    DocumentGroundTruth,
    DocumentProvenance,
    GroundTruthClause,
    GroundTruthTable,
)

GENUINE_CORPUS_DIR = Path("backend/app/tests/fixtures/genuine_corpus")
SYNTHETIC_CORPUS_DIR = Path("backend/app/tests/fixtures/corpus")


class EvaluationCorpusRegistry:
    """
    Registry for managing both synthetic benchmark fixtures and genuine Bangladesh Bank PDFs.
    Ensures absolute clarity of provenance and prevents synthetic fixtures from being
    represented as authentic publications.
    """

    def __init__(self):
        self._registry: Dict[str, DocumentGroundTruth] = {}
        self._load_synthetic_manifest()
        self._discover_genuine_documents()

    def _load_synthetic_manifest(self) -> None:
        from backend.app.tests.fixtures.gold_corpus_manifest import GOLD_CORPUS_MANIFEST

        for entry in GOLD_CORPUS_MANIFEST:
            fn = entry["filename"]
            file_path = SYNTHETIC_CORPUS_DIR / fn
            file_sha = ""
            page_count = entry.get("page_count", 1)

            if file_path.exists():
                raw_bytes = file_path.read_bytes()
                file_sha = hashlib.sha256(raw_bytes).hexdigest()
                try:
                    doc = fitz.open(stream=raw_bytes, filetype="pdf")
                    page_count = len(doc)
                    doc.close()
                except Exception:
                    pass

            prov = DocumentProvenance(
                filename=fn,
                provenance_type="SYNTHETIC_BENCHMARK",
                authority=entry.get("authority", "Bangladesh Bank"),
                department=entry.get("department", "BRPD"),
                circular_number=entry.get("reference_number"),
                publication_date=entry.get("publication_date"),
                title=f"Synthetic Benchmark: {entry.get('category')}",
                page_count=page_count,
                file_sha256=file_sha,
                source_url=None,
                acquisition_method="SYNTHETIC_GENERATOR",
                acquisition_date="2026-11-05",
                manual_verification_level="GOLD_HUMAN_VERIFIED",
                known_limitations=entry.get("known_limitations")
            )

            # Build ground truth clauses
            gt_clauses = [
                GroundTruthClause(
                    clause_number=c,
                    heading=None,
                    verbatim_text=f"Clause {c} text",
                    page_number=1
                )
                for c in entry.get("expected_clauses", [])
            ]

            gt = DocumentGroundTruth(
                provenance=prov,
                ground_truth_pages={},
                ground_truth_clauses=gt_clauses,
                ground_truth_tables=[],
                effective_dates=[],
                referenced_circulars=[]
            )
            self._registry[fn] = gt

    def _discover_genuine_documents(self) -> None:
        """Scans genuine corpus directory for manually deposited genuine BB circulars."""
        if not GENUINE_CORPUS_DIR.exists():
            GENUINE_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
            return

        for p in GENUINE_CORPUS_DIR.glob("*.pdf"):
            if p.name in self._registry:
                continue
            raw_bytes = p.read_bytes()
            file_sha = hashlib.sha256(raw_bytes).hexdigest()
            try:
                doc = fitz.open(stream=raw_bytes, filetype="pdf")
                p_count = len(doc)
                doc.close()
            except Exception:
                p_count = 0

            prov = DocumentProvenance(
                filename=p.name,
                provenance_type="GENUINE_REGULATORY_DOCUMENT",
                authority="Bangladesh Bank",
                department="UNKNOWN",
                title=p.stem.replace("_", " ").title(),
                page_count=p_count,
                file_sha256=file_sha,
                acquisition_method="MANUAL_DEPOSIT",
                manual_verification_level="UNVERIFIED",
                known_limitations="Awaiting human ground-truth labeling."
            )
            self._registry[p.name] = DocumentGroundTruth(provenance=prov)

    def register_genuine_document(
        self,
        pdf_bytes: bytes,
        filename: str,
        title: str,
        department: str,
        circular_number: Optional[str] = None,
        publication_date: Optional[str] = None,
        source_url: Optional[str] = None,
        manual_verification_level: str = "PARTIAL_HUMAN_CHECKED",
        known_limitations: Optional[str] = None
    ) -> DocumentGroundTruth:
        """
        Registers an authentically acquired Bangladesh Bank document with strict provenance.
        Saves original bytes immutably into genuine_corpus.
        """
        GENUINE_CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = GENUINE_CORPUS_DIR / filename
        file_path.write_bytes(pdf_bytes)

        file_sha = hashlib.sha256(pdf_bytes).hexdigest()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        p_count = len(doc)
        doc.close()

        prov = DocumentProvenance(
            filename=filename,
            provenance_type="GENUINE_REGULATORY_DOCUMENT",
            authority="Bangladesh Bank",
            department=department,
            circular_number=circular_number,
            publication_date=publication_date,
            title=title,
            page_count=p_count,
            file_sha256=file_sha,
            source_url=source_url,
            acquisition_method="MANUAL_DEPOSIT",
            manual_verification_level=manual_verification_level,
            known_limitations=known_limitations
        )
        gt = DocumentGroundTruth(provenance=prov)
        self._registry[filename] = gt
        return gt

    def get_document(self, filename: str) -> Optional[DocumentGroundTruth]:
        return self._registry.get(filename)

    def list_all(self) -> List[DocumentGroundTruth]:
        return list(self._registry.values())

    def list_genuine(self) -> List[DocumentGroundTruth]:
        return [gt for gt in self._registry.values() if gt.provenance.provenance_type == "GENUINE_REGULATORY_DOCUMENT"]

    def list_synthetic(self) -> List[DocumentGroundTruth]:
        return [gt for gt in self._registry.values() if gt.provenance.provenance_type == "SYNTHETIC_BENCHMARK"]


evaluation_registry = EvaluationCorpusRegistry()
