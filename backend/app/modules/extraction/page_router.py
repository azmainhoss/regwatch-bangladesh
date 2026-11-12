"""Decides, page by page, how a PDF page gets read (DECISIONS.md 6 and 10).

The decision looks at what is actually on the page: the font names and characters of the
text layer from PyMuPDF's get_text("dict"). Labels such as "English" or "Bangla" on the
source site are not used.

- A clean English text layer is read locally from the PDF (TEXT_LAYER).
- Everything else goes to the page-image reader (VISION):
  - legacy ANSI Bangla fonts (Bijoy family such as SutonnyMJ, NikoshBAN, NokshiStandard);
  - text whose characters look like Bijoy glyph soup even under an unknown font name;
  - broken Bangla (Bangla code points in sequences no real word can have);
  - Bangla Unicode text (decided: every Bangla page is read from the image);
  - pages with almost no text (scans).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

TEXT_LAYER = "TEXT_LAYER"
VISION = "VISION"

# Reasons a page goes to the page-image reader.
REASON_LEGACY_FONT = "legacy_bangla_font"
REASON_LEGACY_GLYPHS = "legacy_bangla_glyphs"
REASON_BROKEN_BANGLA = "broken_bangla"
REASON_BANGLA_UNICODE = "bangla_unicode"
REASON_NEAR_EMPTY = "near_empty"
REASON_CLEAN_TEXT = "clean_text_layer"

BANGLA_REASONS = {REASON_LEGACY_FONT, REASON_LEGACY_GLYPHS, REASON_BROKEN_BANGLA, REASON_BANGLA_UNICODE}

# Fewer visible characters than this means the page is a scan (or blank).
MIN_TEXT_CHARS = 30
# Share of a page's visible characters that makes it a Bangla page.
BANGLA_SHARE = 0.15

# Legacy (ANSI) Bangla font names. Subset prefixes like "ABCDEF+" are stripped first.
_LEGACY_FONT_WORDS = ("sutonny", "nokshi", "bijoy", "nikoshban", "nikosh-legacy", "nikoshlegacy",
                      "ansi", "chandrabati", "boishakhi", "lucidabangla", "lucida bangla")
_MJ_SUFFIX = re.compile(r"mj(?:$|[^a-z])")

# Characters that ANSI Bangla fonts map Bangla glyphs onto. English text almost never uses them.
_LEGACY_GLYPH_CHARS = set("‡†Ö¨©ª¯¶Ô×ØÕÐÑÒÓ°±²³´µ·¸¹º¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏ")

# Bangla block and its character classes.
_BN_START, _BN_END = 0x0980, 0x09FF
_BN_SIGNS = set(range(0x0981, 0x0984)) | {0x09BC} | set(range(0x09BE, 0x09CE)) | {0x09D7, 0x09E2, 0x09E3}
_BN_BASES = (set(range(0x0985, 0x098D)) | {0x098F, 0x0990} | set(range(0x0993, 0x09A9))
             | set(range(0x09AA, 0x09B1)) | {0x09B2} | set(range(0x09B6, 0x09BA))
             | {0x09BD, 0x09CE, 0x09DC, 0x09DD, 0x09DF, 0x09E0, 0x09E1, 0x09F0, 0x09F1})
_ZW = {0x200C, 0x200D}


@dataclass
class PageRoute:
    route: str  # TEXT_LAYER or VISION
    reason: str
    text: str  # the PDF's own text layer (kept for reference even when the page goes to VISION)
    fonts: List[str] = field(default_factory=list)
    line_boxes: List[Dict[str, Any]] = field(default_factory=list)
    language: Optional[str] = None  # "en", "bn" or None when unknown (scan)

    @property
    def is_bangla(self) -> bool:
        return self.reason in BANGLA_REASONS


def _clean_font_name(name: str) -> str:
    name = (name or "").strip()
    if "+" in name[:8]:
        name = name.split("+", 1)[1]
    return name


def is_legacy_font(name: str) -> bool:
    lower = _clean_font_name(name).lower()
    if any(word in lower for word in _LEGACY_FONT_WORDS):
        return True
    return bool(_MJ_SUFFIX.search(lower))


def looks_like_legacy_glyphs(text: str) -> bool:
    hits = sum(1 for c in text if c in _LEGACY_GLYPH_CHARS)
    letters = sum(1 for c in text if not c.isspace())
    return hits >= 5 and hits / max(letters, 1) >= 0.01


def bangla_char_count(text: str) -> int:
    return sum(1 for c in text if _BN_START <= ord(c) <= _BN_END)


def broken_bangla_count(text: str) -> int:
    """Counts vowel signs, hasant or nukta that do not follow a Bangla letter.
    A good Unicode text layer has (almost) none; a broken font mapping has many."""
    bad = 0
    prev = None
    for c in text:
        code = ord(c)
        if code in _BN_SIGNS:
            if prev is None or not (prev in _BN_BASES or prev in _BN_SIGNS or prev in _ZW):
                bad += 1
        elif 0xE000 <= code <= 0xF8FF or code == 0xFFFD:
            # Private-use or replacement characters: glyphs the font never mapped to Unicode.
            bad += 1
        prev = code
    return bad


def _norm_box(bbox, width: float, height: float) -> List[int]:
    """PDF (x0, y0, x1, y1) in points -> Gemini order [ymin, xmin, ymax, xmax], 0-1000."""
    x0, y0, x1, y1 = bbox

    def scale(v: float, size: float) -> int:
        return max(0, min(1000, round(v / size * 1000))) if size else 0

    return [scale(y0, height), scale(x0, width), scale(y1, height), scale(x1, width)]


def text_layer_lines(
    page_dict: Dict[str, Any],
    width: float,
    height: float,
    words: Optional[Sequence[Sequence[Any]]] = None,
) -> List[Dict[str, Any]]:
    """One entry per text line: its text and its box (0-1000, [ymin, xmin, ymax, xmax]).

    When PyMuPDF's `get_text("words")` output is given, each line also lists its words with
    their own boxes ({"text", "box_2d"}), so a quote that starts or ends mid-line can be
    highlighted on exactly the words it covers.
    """
    by_line: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for w in words or []:
        if len(w) < 7 or not str(w[4]).strip():
            continue
        by_line.setdefault((int(w[5]), int(w[6])), []).append(
            {"text": str(w[4]), "box_2d": _norm_box(w[:4], width, height)}
        )
    lines: List[Dict[str, Any]] = []
    for b_idx, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        block_no = block.get("number", b_idx)
        for l_idx, line in enumerate(block.get("lines", [])):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if not text.strip():
                continue
            entry: Dict[str, Any] = {"text": text.strip(), "box_2d": _norm_box(line["bbox"], width, height)}
            line_words = by_line.get((block_no, l_idx))
            if line_words:
                entry["words"] = line_words
            lines.append(entry)
    return lines


def route_page(page) -> PageRoute:
    """Reads one PyMuPDF page's text layer and decides how the page should be read."""
    text = page.get_text("text")
    page_dict = page.get_text("dict")
    rect = page.rect

    fonts: List[str] = []
    legacy_chars = 0
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []) if block.get("type", 0) == 0 else []:
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                if span_text.strip():
                    name = _clean_font_name(span.get("font", ""))
                    if name and name not in fonts:
                        fonts.append(name)
                    if is_legacy_font(name):
                        legacy_chars += sum(1 for c in span_text if not c.isspace())

    visible = "".join(c for c in text if not c.isspace())
    if len(visible) < MIN_TEXT_CHARS:
        return PageRoute(VISION, REASON_NEAR_EMPTY, text, fonts)

    # A short Bangla letterhead on an English page does not send the page away;
    # a real share of Bangla (legacy or Unicode) does.
    if legacy_chars >= MIN_TEXT_CHARS or legacy_chars / len(visible) >= BANGLA_SHARE:
        return PageRoute(VISION, REASON_LEGACY_FONT, text, fonts, language="bn")

    if looks_like_legacy_glyphs(text):
        return PageRoute(VISION, REASON_LEGACY_GLYPHS, text, fonts, language="bn")

    bangla = bangla_char_count(text)
    if bangla:
        broken = broken_bangla_count(text)
        if broken >= 3 and broken / bangla >= 0.02:
            return PageRoute(VISION, REASON_BROKEN_BANGLA, text, fonts, language="bn")
        if bangla / len(visible) >= BANGLA_SHARE:
            return PageRoute(VISION, REASON_BANGLA_UNICODE, text, fonts, language="bn")

    lines = text_layer_lines(page_dict, rect.width, rect.height, page.get_text("words"))
    return PageRoute(TEXT_LAYER, REASON_CLEAN_TEXT, text, fonts, lines, language="en")


def text_layer_lines_by_page(pdf_bytes: bytes) -> Dict[int, List[Dict[str, Any]]]:
    """Line and word boxes for every page of a PDF that is read from its text layer, by page number.

    Pages that go to page-image reading are left out: their boxes come from that reading.
    """
    import pymupdf

    out: Dict[int, List[Dict[str, Any]]] = {}
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(len(doc)):
            route = route_page(doc[i])
            if route.route == TEXT_LAYER and route.line_boxes:
                out[i + 1] = route.line_boxes
    return out


def has_word_boxes(line_boxes: Any) -> bool:
    """True when stored line boxes already carry per-word boxes."""
    return isinstance(line_boxes, list) and any(isinstance(l, dict) and l.get("words") for l in line_boxes)
