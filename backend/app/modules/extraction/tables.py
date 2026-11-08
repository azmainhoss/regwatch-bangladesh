import io
import re
from typing import Any, Dict, List, Optional, Tuple
import pdfplumber
import pymupdf as fitz

from backend.app.core.logging import logger


class TableExtractor:
    """
    Extracts structured tabular data from PDF pages.
    Preserves exact row-column matrix, headers, financial thresholds,
    and returns both raw and normalized record formats.
    """

    FINANCIAL_PATTERN = re.compile(
        r"(\d+(\.\d+)?\s*(%|percent|crore|lakh|bdt|tk|\$|basis points|bps))|"
        r"(\b\d{1,3}(,\d{3})+(\.\d+)?\b)|"
        r"(\b(capital adequacy|provisioning|interest rate|tier 1|tier 2|crar)\b)",
        re.IGNORECASE
    )

    @classmethod
    def extract_tables_from_page(
        cls,
        pdf_bytes: bytes,
        page_number: int,
        raw_page_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Extracts all tables on a specific 1-indexed page number using dual strategies:
        1. Visual grid extraction via pdfplumber.
        2. Text-aligned grid extraction for monospace or rule-bordered ASCII tables.
        """
        extracted_tables: List[Dict[str, Any]] = []

        # Safeguard: skip heavy pdfplumber visual grid extraction on files > 2MB to protect RAM
        if len(pdf_bytes) > 2_000_000:
            return extracted_tables

        # Strategy 1: pdfplumber visual extraction
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if page_number <= len(pdf.pages):
                    plumber_page = pdf.pages[page_number - 1]
                    tables = plumber_page.extract_tables()
                    for idx, tbl in enumerate(tables):
                        if not tbl or len(tbl) < 2:
                            continue
                        table_dict = cls._process_raw_table_matrix(
                            raw_matrix=tbl,
                            page_number=page_number,
                            table_index=idx + 1,
                            method="PDFPLUMBER_VECTOR_GRID",
                            bbox=None
                        )
                        if table_dict:
                            extracted_tables.append(table_dict)
        except Exception as e:
            logger.debug(f"pdfplumber table extraction note on page {page_number}: {e}")

        # Strategy 2: If no visual tables found, check PyMuPDF find_tables()
        if not extracted_tables:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                if page_number <= len(doc):
                    fitz_page = doc[page_number - 1]
                    tabs = fitz_page.find_tables()
                    for idx, tab in enumerate(tabs.tables):
                        mat = tab.extract()
                        if mat and len(mat) >= 2:
                            bbox = tab.bbox
                            table_dict = cls._process_raw_table_matrix(
                                raw_matrix=mat,
                                page_number=page_number,
                                table_index=len(extracted_tables) + idx + 1,
                                method="PYMUPDF_TABLE_FINDER",
                                bbox={"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]}
                            )
                            if table_dict:
                                extracted_tables.append(table_dict)
                doc.close()
            except Exception as e:
                logger.debug(f"PyMuPDF find_tables note on page {page_number}: {e}")

        # Strategy 3: Text-aligned / ASCII rule-bordered table extraction
        if not extracted_tables and raw_page_text:
            text_tables = cls._extract_text_aligned_tables(raw_page_text, page_number)
            extracted_tables.extend(text_tables)

        return extracted_tables

    @classmethod
    def _process_raw_table_matrix(
        cls,
        raw_matrix: List[List[Optional[str]]],
        page_number: int,
        table_index: int,
        method: str,
        bbox: Optional[Dict[str, float]] = None
    ) -> Optional[Dict[str, Any]]:
        """Cleans and standardizes raw 2D grid matrix into structured table payload."""
        cleaned_rows: List[List[str]] = []
        for row in raw_matrix:
            cleaned_row = [(cell or "").strip().replace("\n", " ") for cell in row]
            # Ignore entirely empty rows
            if any(cell for cell in cleaned_row):
                cleaned_rows.append(cleaned_row)

        if len(cleaned_rows) < 2:
            return None

        headers = cleaned_rows[0]
        data_rows = cleaned_rows[1:]

        # Normalize records (header -> value map)
        normalized_records: List[Dict[str, str]] = []
        for r in data_rows:
            record: Dict[str, str] = {}
            for col_idx, h in enumerate(headers):
                h_name = h if h else f"col_{col_idx + 1}"
                val = r[col_idx] if col_idx < len(r) else ""
                record[h_name] = val
            normalized_records.append(record)

        # Detect financial contents and extract exact figures
        all_text = " ".join([" ".join(row) for row in cleaned_rows])
        financial_matches = [m.group(0).strip() for m in cls.FINANCIAL_PATTERN.finditer(all_text)]
        has_financial = len(financial_matches) > 0

        # Detect potential merged cells (None or empty in raw matrix where row length is inconsistent)
        merged_cells_detected = any(
            (cell is None or cell == "") and idx > 0
            for row in raw_matrix for idx, cell in enumerate(row)
        ) and not (all(cell == "" for cell in raw_matrix[-1]))

        # Calculate structure quality
        col_counts = [len(r) for r in cleaned_rows]
        is_rectangular = len(set(col_counts)) == 1
        quality_score = 1.0 if is_rectangular else 0.70
        if merged_cells_detected:
            quality_score = min(quality_score, 0.80)

        return {
            "table_index": table_index,
            "page_number": page_number,
            "extraction_method": method,
            "headers": headers,
            "raw_rows": cleaned_rows,
            "normalized_records": normalized_records,
            "row_count": len(cleaned_rows),
            "col_count": max(col_counts) if col_counts else 0,
            "has_financial_data": has_financial,
            "financial_figures": list(dict.fromkeys(financial_matches)),
            "merged_cells_detected": merged_cells_detected,
            "quality_score": quality_score,
            "bbox": bbox,
            "needs_review": quality_score < 0.85 or not is_rectangular
        }

    @classmethod
    def _extract_text_aligned_tables(
        cls,
        raw_text: str,
        page_number: int
    ) -> List[Dict[str, Any]]:
        """
        Parses ASCII / text-rule formatted tables often seen in banking circular annexures.
        Example:
        ---------------------------------------------------------------------
        Category            Outstanding Balance      Required Provision
        ---------------------------------------------------------------------
        Stage 1                   45000.50                 450.00
        ---------------------------------------------------------------------
        """
        tables = []
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        
        in_table = False
        table_lines: List[str] = []
        divider_pattern = re.compile(r"^[-=_\s]{6,}$")
        table_title_pattern = re.compile(r"^(Table\s+\d+|Annexure|Schedule|তপশিল)", re.IGNORECASE)

        for i, line in enumerate(lines):
            is_divider = bool(divider_pattern.match(line))
            is_new_table_title = bool(table_title_pattern.match(line))

            if is_new_table_title and in_table and len(table_lines) >= 3:
                # Flush previous table
                parsed = cls._parse_ascii_table_lines(table_lines, page_number, len(tables) + 1)
                if parsed:
                    tables.append(parsed)
                table_lines = [line]
                in_table = True
                continue

            if is_divider:
                if not in_table:
                    in_table = True
                    table_lines = []
                    if i > 0 and len(lines[i-1]) > 5:
                        table_lines.append(lines[i-1])
                else:
                    # Closing divider or internal divider
                    if i + 1 < len(lines) and not divider_pattern.match(lines[i+1]) and not table_title_pattern.match(lines[i+1]):
                        # If table already has 3+ lines, check if next line is a separate section
                        table_lines.append(line)
                    else:
                        in_table = False
                        if len(table_lines) >= 3:
                            parsed = cls._parse_ascii_table_lines(table_lines, page_number, len(tables) + 1)
                            if parsed:
                                tables.append(parsed)
                        table_lines = []
            elif in_table:
                table_lines.append(line)

        # Catch if table ran until end
        if in_table and len(table_lines) >= 3:
            parsed = cls._parse_ascii_table_lines(table_lines, page_number, len(tables) + 1)
            if parsed:
                tables.append(parsed)

        return tables

    @classmethod
    def _parse_ascii_table_lines(
        cls,
        lines: List[str],
        page_number: int,
        table_idx: int
    ) -> Optional[Dict[str, Any]]:
        matrix: List[List[str]] = []
        for line in lines:
            if re.match(r"^[-=_]{4,}$", line):
                continue
            # Split by 2 or more spaces or tabs
            cells = [c.strip() for c in re.split(r"(\s{2,}|\t+|\|)", line) if c.strip() and c.strip() != "|"]
            if len(cells) >= 2:
                matrix.append(cells)

        if len(matrix) >= 2:
            return cls._process_raw_table_matrix(
                raw_matrix=matrix,
                page_number=page_number,
                table_index=table_idx,
                method="TEXT_ALIGNED_GRID",
                bbox=None
            )
        return None
