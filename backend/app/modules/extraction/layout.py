import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClauseNode(BaseModel):
    clause_number: str
    parent_clause: Optional[str] = None
    level: int = 1
    heading: Optional[str] = None
    text: str
    page_number: int
    subclauses: List["ClauseNode"] = Field(default_factory=list)


class DocumentLayout(BaseModel):
    header_block: Optional[str] = None
    subject: Optional[str] = None
    salutation: Optional[str] = None
    clauses: List[ClauseNode] = Field(default_factory=list)
    annexures: List[Dict[str, Any]] = Field(default_factory=list)
    signatories: List[str] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)


class LayoutAwareExtractor:
    """
    Parses raw page text into a hierarchical regulatory document structure.
    Preserves relationships between clauses, subclauses, annexures, and footnotes.
    Supports complex multi-level numbering (1, 1.1, 1.1.1, 1.2(a)) in English and Bengali.
    """

    # Multi-level clause regex patterns
    LEVEL_3_DEEP_PATTERN = re.compile(
        r"^(\d{1,2}\.\d{1,2}\.\d{1,2}|[১২৩৪৫৬৭৮৯০]{1,2}\.[১২৩৪৫৬৭৮৯০]{1,2}\.[১২৩৪৫৬৭৮৯০]{1,2})\.?\s+(.*)$"
    )
    LEVEL_2_PAREN_PATTERN = re.compile(
        r"^(\d{1,2}\.\d{1,2}\s*\([a-z0-9]+\)|[১২৩৪৫৬৭৮৯০]{1,2}\.[১২৩৪৫৬৭৮৯০]{1,2}\s*\([ক-হ১২৩৪৫৬৭৮৯০]+\))\.?\s+(.*)$",
        re.IGNORECASE
    )
    LEVEL_2_NUM_PATTERN = re.compile(
        r"^(\d{1,2}\.\d{1,2}|[১২৩৪৫৬৭৮৯০]{1,2}\.[১২৩৪৫৬৭৮৯০]{1,2})\.?\s+(.*)$"
    )
    LEVEL_1_PAREN_PATTERN = re.compile(
        r"^(\d{1,2}\s*\([a-z0-9]+\)|[১২৩৪৫৬৭৮৯০]{1,2}\s*\([ক-হ১২৩৪৫৬৭৮৯০]+\))\.?\s+(.*)$",
        re.IGNORECASE
    )
    LEVEL_1_NUM_PATTERN = re.compile(
        r"^(\d{1,2}|[১২৩৪৫৬৭৮৯০]{1,2})\.\s+(.*)$"
    )
    LETTER_SUB_PATTERN = re.compile(
        r"^(\([a-z0-9]+\)|\([ক-হ১২৩৪৫৬৭৮৯০]+\)|[a-z]\))\s+(.*)$",
        re.IGNORECASE
    )
    BULLET_PATTERN = re.compile(r"^([•\-\*])\s+(.*)$")

    SUBJECT_PATTERN = re.compile(r"^(Subject|বিষয়|বিষয়ঃ):\s*(.*)$", re.IGNORECASE)
    ANNEXURE_PATTERN = re.compile(r"^(Annexure|Schedule|Appendix|সংযোজনী|তপশিল)[\s\-\:]*(.*)$", re.IGNORECASE)
    SIGNATORY_PATTERN = re.compile(r"^(Yours faithfully|Yours truly|Sincerely|নিবেদক|স্বাক্ষরিত)[\s,]*$", re.IGNORECASE)
    FOOTNOTE_PATTERN = re.compile(r"^(\*+|\d+\/|\bNote\b|\bবিশেষ দ্রষ্টব্য\b|\bবিঃ দ্রঃ\b|\bN\.B\.:)\s*(.*)$", re.IGNORECASE)
    RUNNING_HEADER_FOOTER = re.compile(r"^(Page\s+\d+(\s+of\s+\d+)?|পৃষ্ঠা\s+[\u09E6-\u09EF]+|\d+)$", re.IGNORECASE)

    @classmethod
    def parse_document_pages_layout(
        cls,
        pages: List[Dict[str, Any]]
    ) -> DocumentLayout:
        """
        Parses all pages of a document into a consolidated layout hierarchy.
        """
        layout = DocumentLayout()
        root_clauses: List[ClauseNode] = []
        clause_map: Dict[str, ClauseNode] = {}  # clause_number -> ClauseNode

        current_l1: Optional[ClauseNode] = None
        current_l2: Optional[ClauseNode] = None
        current_l3: Optional[ClauseNode] = None

        for page in pages:
            page_no = page.get("page_number", 1)
            raw_text = page.get("cleaned_text") or page.get("raw_text", "")
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

            for line in lines:
                # Running headers and solitary page numbers (skip from clause text)
                if cls.RUNNING_HEADER_FOOTER.match(line):
                    continue

                # 1. Subject Detection
                subj_match = cls.SUBJECT_PATTERN.match(line)
                if subj_match and not layout.subject:
                    layout.subject = subj_match.group(2).strip()
                    continue

                # 2. Annexure Detection
                annex_match = cls.ANNEXURE_PATTERN.match(line)
                if annex_match:
                    layout.annexures.append({
                        "title": line,
                        "page_number": page_no,
                        "header": annex_match.group(2).strip()
                    })
                    continue

                # 3. Signatory Detection
                if cls.SIGNATORY_PATTERN.match(line):
                    layout.signatories.append(line)
                    continue

                # 4. Footnote Detection
                fn_match = cls.FOOTNOTE_PATTERN.match(line)
                if fn_match:
                    layout.footnotes.append(line)
                    continue

                # 5. Deep Level 3: e.g. "1.1.1 Sub-clause text" or "১.১.১ অনুচ্ছেদ"
                l3_deep_match = cls.LEVEL_3_DEEP_PATTERN.match(line)
                if l3_deep_match:
                    num = l3_deep_match.group(1).strip()
                    body = l3_deep_match.group(2).strip()
                    # Parent is first two parts, e.g. "1.1" from "1.1.1"
                    parts = num.split(".")
                    parent_num = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else (current_l2.clause_number if current_l2 else None)

                    node = ClauseNode(
                        clause_number=num,
                        parent_clause=parent_num,
                        level=3,
                        text=body,
                        page_number=page_no
                    )
                    clause_map[num] = node
                    current_l3 = node
                    parent_node = clause_map.get(parent_num) if parent_num else current_l2
                    if parent_node:
                        parent_node.subclauses.append(node)
                    elif current_l1:
                        current_l1.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 6. Level 2 with attached letter: e.g. "1.2(a) Special conditions" or "১.২(ক) বিশেষ শর্ত"
                l2_paren_match = cls.LEVEL_2_PAREN_PATTERN.match(line)
                if l2_paren_match:
                    num = l2_paren_match.group(1).replace(" ", "").strip()
                    body = l2_paren_match.group(2).strip()
                    parent_num = num.split("(")[0]
                    top_parent_num = parent_num.split(".")[0] if "." in parent_num else parent_num

                    node = ClauseNode(
                        clause_number=num,
                        parent_clause=parent_num,
                        level=3,
                        text=body,
                        page_number=page_no
                    )
                    clause_map[num] = node
                    parent_node = clause_map.get(parent_num) or clause_map.get(top_parent_num) or current_l1
                    if parent_node:
                        parent_node.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 7. Level 2 Numeric: e.g. "1.1 Stage 1" or "১.১ প্রথম ধাপ"
                l2_num_match = cls.LEVEL_2_NUM_PATTERN.match(line)
                if l2_num_match:
                    num = l2_num_match.group(1).strip()
                    body = l2_num_match.group(2).strip()
                    parent_num = num.split(".")[0] if "." in num else (current_l1.clause_number if current_l1 else None)

                    node = ClauseNode(
                        clause_number=num,
                        parent_clause=parent_num,
                        level=2,
                        text=body,
                        page_number=page_no
                    )
                    clause_map[num] = node
                    current_l2 = node
                    current_l3 = None
                    parent_node = clause_map.get(parent_num) or current_l1
                    if parent_node:
                        parent_node.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 8. Level 1 Numeric: e.g. "1. Master Policy:" or "১. প্রধান নীতিমালা:"
                l1_num_match = cls.LEVEL_1_NUM_PATTERN.match(line)
                if l1_num_match:
                    num = l1_num_match.group(1).strip()
                    body = l1_num_match.group(2).strip()

                    heading = None
                    if ":" in body:
                        parts = body.split(":", 1)
                        heading = parts[0].strip()
                        body = parts[1].strip()

                    node = ClauseNode(
                        clause_number=num,
                        parent_clause=None,
                        level=1,
                        heading=heading,
                        text=body,
                        page_number=page_no
                    )
                    clause_map[num] = node
                    current_l1 = node
                    current_l2 = None
                    current_l3 = None
                    root_clauses.append(node)
                    continue

                # 9. Standalone letter subclauses: e.g. "(a) Condition", "(ক) শর্ত"
                letter_match = cls.LETTER_SUB_PATTERN.match(line)
                if letter_match:
                    num = letter_match.group(1).strip()
                    body = letter_match.group(2).strip()
                    parent_ref = (
                        current_l3.clause_number if current_l3
                        else (current_l2.clause_number if current_l2
                        else (current_l1.clause_number if current_l1 else None))
                    )
                    full_num = f"{parent_ref}{num}" if parent_ref else num

                    node = ClauseNode(
                        clause_number=full_num,
                        parent_clause=parent_ref,
                        level=3,
                        text=body,
                        page_number=page_no
                    )
                    clause_map[full_num] = node
                    if current_l2:
                        current_l2.subclauses.append(node)
                    elif current_l1:
                        current_l1.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 10. Continuation text: unnumbered paragraph belongs to active clause
                if current_l3:
                    current_l3.text += " " + line
                elif current_l2:
                    current_l2.text += " " + line
                elif current_l1:
                    current_l1.text += " " + line
                else:
                    if not layout.header_block:
                        layout.header_block = line
                    else:
                        layout.header_block += "\n" + line

        layout.clauses = root_clauses
        return layout
