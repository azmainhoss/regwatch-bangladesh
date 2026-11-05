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
    Preserves relationships between clauses, subclauses, and annexures.
    """

    # Regex patterns for clause numbering
    LEVEL_1_PATTERN = re.compile(r"^(\d{1,2}|[১২৩৪৫৬৭৮৯০]{1,2})\.\s+(.*)$")
    LEVEL_2_PATTERN = re.compile(r"^(\d{1,2}\.\d{1,2}|[১২৩৪৫৬৭৮৯০]{1,2}\.[১২৩৪৫৬৭৮৯০]{1,2})\s+(.*)$")
    LEVEL_3_PATTERN = re.compile(r"^(\([a-z]\)|\([a-z0-9]+\)|\([ক-হ]\)|[a-z]\))\s+(.*)$", re.IGNORECASE)
    BULLET_PATTERN = re.compile(r"^([•\-\*])\s+(.*)$")
    
    SUBJECT_PATTERN = re.compile(r"^(Subject|বিষয়|বিষয়ঃ):\s*(.*)$", re.IGNORECASE)
    ANNEXURE_PATTERN = re.compile(r"^(Annexure|Schedule|Appendix|সংযোজনী|তপশিল)[\s\-\:]*(.*)$", re.IGNORECASE)
    SIGNATORY_PATTERN = re.compile(r"^(Yours faithfully|Yours truly|Sincerely|নিবেদক|স্বাক্ষরিত)[\s,]*$", re.IGNORECASE)

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
        
        current_l1: Optional[ClauseNode] = None
        current_l2: Optional[ClauseNode] = None

        for page in pages:
            page_no = page.get("page_number", 1)
            raw_text = page.get("cleaned_text") or page.get("raw_text", "")
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

            for line in lines:
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

                # 4. Level 2 Clause: e.g. "1.1 Mandate"
                l2_match = cls.LEVEL_2_PATTERN.match(line)
                if l2_match:
                    num = l2_match.group(1).strip()
                    body = l2_match.group(2).strip()
                    parent_num = num.split(".")[0] if "." in num else (current_l1.clause_number if current_l1 else None)
                    
                    node = ClauseNode(
                        clause_number=num,
                        parent_clause=parent_num,
                        level=2,
                        text=body,
                        page_number=page_no
                    )
                    current_l2 = node
                    if current_l1:
                        current_l1.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 5. Level 1 Clause: e.g. "1. Master Policy"
                l1_match = cls.LEVEL_1_PATTERN.match(line)
                if l1_match:
                    num = l1_match.group(1).strip()
                    body = l1_match.group(2).strip()
                    
                    # Split heading if colon present: "1. Staging Framework: All banks..."
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
                    current_l1 = node
                    current_l2 = None
                    root_clauses.append(node)
                    continue

                # 6. Level 3 Subclause: e.g. "(a) Stage 1: Performing"
                l3_match = cls.LEVEL_3_PATTERN.match(line)
                if l3_match:
                    num = l3_match.group(1).strip()
                    body = l3_match.group(2).strip()
                    parent_ref = current_l2.clause_number if current_l2 else (current_l1.clause_number if current_l1 else None)
                    full_num = f"{parent_ref}{num}" if parent_ref else num

                    node = ClauseNode(
                        clause_number=full_num,
                        parent_clause=parent_ref,
                        level=3,
                        text=body,
                        page_number=page_no
                    )
                    if current_l2:
                        current_l2.subclauses.append(node)
                    elif current_l1:
                        current_l1.subclauses.append(node)
                    else:
                        root_clauses.append(node)
                    continue

                # 7. Append continuous paragraph text to active clause
                if current_l2:
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
