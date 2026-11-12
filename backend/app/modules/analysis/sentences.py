"""Sentence IDs for quotes (DECISIONS.md 7).

The model never types a quote. Each page's text is split into sentences with stable IDs such as
`p3.s12` (page 3, sentence 12), the model is shown the text with those IDs, and it answers with a
list of IDs. Code then copies the exact text for those IDs out of the stored page text.

A sentence ends at an English full stop, question or exclamation mark followed by a space, at the
Bangla full stop (U+0964 "।") or double danda (U+0965), at a blank line, at a line break after ";"
or ":", before a line that starts a new list item, or after a short line (heading, letterhead)
followed by a capitalised line. Table rows (lines with " | ") stand alone.
Splitting is deterministic, so the same page text always gives the same IDs.

Where the page has `line_boxes` (one box per printed line), each sentence also gets the indexes
and boxes of the lines it covers, so a viewer can highlight the quote on the page image.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BANGLA_STOPS = "।॥"  # । ॥

# Words that end with "." without ending a sentence.
_ABBREVIATIONS = {
    "no", "nos", "sl", "ref", "sec", "secs", "art", "para", "paras", "cl", "sub", "vol", "ch", "fig",
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ltd", "co", "corp", "inc", "pvt", "govt",
    "dept", "deptt", "div", "u/s", "e.g", "i.e", "etc", "viz", "vs", "approx", "dt", "dtd", "tk",
    "rs", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "a/c", "acc", "max", "min", "amt", "gm", "dgm", "agm", "ed", "md", "ceo",
}

# A line that opens a new list item: "1.", "1.1", "(a)", "a)", "(iv)", "ক)", "১.", "-", "•".
_LIST_START = re.compile(
    r"^\s*(?:"
    r"[•●▪\-–\*]\s"
    r"|\(?(?:[0-9০-৯]{1,3}(?:\.[0-9০-৯]{1,3})*|[a-zA-Z]|[ivxlcIVXLC]{1,5}|[ক-হ])[\.\)]\s"
    r"|\((?:[0-9০-৯]{1,3}|[a-zA-Z]|[ivxlcIVXLC]{1,5}|[ক-হ])\)\s"
    r")"
)

# The token right before a "." that should not end a sentence: list numbers, single letters, roman numerals.
_NON_TERMINAL_TOKEN = re.compile(r"^\(?(?:[0-9০-৯]{1,3}(?:\.[0-9০-৯]{1,3})*|[a-zA-Z]|[ivxlcIVXLC]{1,5})$")

_SHORT_LINE = 60  # characters; printed prose lines in circulars are longer than this

_ID_PATTERN = re.compile(r"^p(\d+)\.s(\d+)$")


@dataclass
class Sentence:
    id: str
    page_number: int
    index: int  # 1-based within the page
    start: int  # character offsets into the page text
    end: int
    text: str  # exact page text[start:end]
    line_indexes: List[int] = field(default_factory=list)
    boxes: List[List[int]] = field(default_factory=list)


@dataclass
class QuoteSpan:
    """The result of turning a list of sentence IDs back into text."""
    ok: bool
    quote: str = ""
    page_number: Optional[int] = None
    sentence_ids: List[str] = field(default_factory=list)
    unknown_ids: List[str] = field(default_factory=list)
    fragments: List[Dict[str, Any]] = field(default_factory=list)  # [{page_number, text, sentence_ids}]
    boxes: List[Dict[str, Any]] = field(default_factory=list)  # [{page_number, line_index, box_2d}]
    error: Optional[str] = None


def _token_before(text: str, pos: int) -> str:
    """The word that ends right before position `pos` (which holds the full stop)."""
    start = pos
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return text[start:pos]


def _is_terminal_period(text: str, pos: int) -> bool:
    token = _token_before(text, pos)
    bare = token.lstrip("(\"'[").lower()
    if not bare:
        return False
    if bare in _ABBREVIATIONS or bare.rstrip(".") in _ABBREVIATIONS:
        return False
    if _NON_TERMINAL_TOKEN.match(token):
        return False
    # Initials such as "A.K." or "U.S."
    if re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", bare):
        return False
    return True


def split_sentence_spans(text: str) -> List[Tuple[int, int]]:
    """Splits page text into (start, end) spans of sentences, trimmed of surrounding whitespace."""
    if not text:
        return []
    cuts: List[int] = []  # positions where a new sentence starts (exclusive end of the previous)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in BANGLA_STOPS:
            j = i + 1
            while j < n and text[j] in BANGLA_STOPS:
                j += 1
            cuts.append(j)
            i = j
            continue
        if ch in ".?!":
            j = i + 1
            while j < n and text[j] in ".?!\"')]’”":
                j += 1
            at_break = j >= n or text[j].isspace()
            if at_break and (ch != "." or _is_terminal_period(text, i)):
                cuts.append(j)
            i = j
            continue
        if ch == "\n":
            # Blank line, a line break after ";" or ":", or a new list item / table row.
            nxt_end = text.find("\n", i + 1)
            next_line = text[i + 1: nxt_end if nxt_end != -1 else n]
            this_start = text.rfind("\n", 0, i) + 1
            this_line = text[this_start:i]
            prev = this_line.rstrip(" \t")
            if (
                not next_line.strip()
                or (prev and prev[-1] in ";:")
                or _LIST_START.match(next_line)
                or " | " in next_line
                or " | " in this_line
                # A short line followed by a capitalised line is a heading or letterhead line
                # ("BANGLADESH BANK", "Date: 27 November 2024", "Dear Sir,"), not wrapped prose.
                or (len(this_line.strip()) < _SHORT_LINE and next_line.lstrip()[:1].isupper())
            ):
                cuts.append(i + 1)
        i += 1

    spans: List[Tuple[int, int]] = []
    start = 0
    for cut in cuts + [n]:
        if cut <= start:
            continue
        s, e = start, cut
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s and any(not c.isspace() for c in text[s:e]):
            spans.append((s, e))
        start = cut
    return spans


def split_sentences(text: str) -> List[str]:
    """Convenience: the sentence strings of a text."""
    return [text[s:e] for s, e in split_sentence_spans(text)]


@dataclass
class _LineSpan:
    index: int  # position in the page's line_boxes list
    start: int  # character offsets of the line's text in the page text
    end: int
    box: Optional[List[int]]
    words: List[Tuple[int, int, List[int]]]  # (start, end, box) of each word, in page-text offsets


def _clean_box(box: Any) -> Optional[List[int]]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        return [int(v) for v in box]
    except (TypeError, ValueError):
        return None


def _word_offsets(line_text: str, line_start: int, words: Any) -> List[Tuple[int, int, List[int]]]:
    """Finds each word of a line inside the line text, in order. Words that cannot be found are skipped."""
    found: List[Tuple[int, int, List[int]]] = []
    if not isinstance(words, list):
        return found
    cursor = 0
    for word in words:
        if not isinstance(word, dict):
            continue
        w_text = str(word.get("text") or "").strip()
        box = _clean_box(word.get("box_2d"))
        if not w_text or box is None:
            continue
        pos = line_text.find(w_text, cursor)
        if pos == -1:
            continue
        cursor = pos + len(w_text)
        found.append((line_start + pos, line_start + cursor, box))
    return found


def _line_offsets(page_text: str, line_boxes: Optional[Sequence[Dict[str, Any]]]) -> List[_LineSpan]:
    """Finds each box line's text in the page text, in order."""
    found: List[_LineSpan] = []
    if not line_boxes:
        return found
    cursor = 0
    for idx, line in enumerate(line_boxes):
        if not isinstance(line, dict):
            continue
        line_text = str(line.get("text") or "").strip()
        if not line_text:
            continue
        pos = page_text.find(line_text, cursor)
        if pos == -1:
            pos = page_text.find(line_text)
            if pos == -1:
                continue
        else:
            cursor = pos + len(line_text)
        found.append(_LineSpan(
            index=idx,
            start=pos,
            end=pos + len(line_text),
            box=_clean_box(line.get("box_2d")),
            words=_word_offsets(line_text, pos, line.get("words")),
        ))
    return found


def _box_for_span(line: _LineSpan, start: int, end: int) -> Optional[List[int]]:
    """The part of a line's box that the text span [start, end) covers.

    Uses the line's word boxes when there are any (English text-layer pages), so a sentence
    that starts or ends mid-line is marked on its own words only; otherwise the whole line box.
    """
    if line.words:
        hit = [box for ws, we, box in line.words if ws < end and we > start]
        if hit:
            return [
                min(b[0] for b in hit),
                min(b[1] for b in hit),
                max(b[2] for b in hit),
                max(b[3] for b in hit),
            ]
    return list(line.box) if line.box else None


class SentenceIndex:
    """All sentences of a document, keyed by ID."""

    def __init__(self) -> None:
        self.sentences: Dict[str, Sentence] = {}
        self.pages: Dict[int, str] = {}
        self.order: Dict[int, List[str]] = {}

    @classmethod
    def build(cls, pages: Iterable[Dict[str, Any]]) -> "SentenceIndex":
        index = cls()
        for page in sorted(pages, key=lambda p: p.get("page_number", 1)):
            p_no = int(page.get("page_number", 1))
            text = page.get("cleaned_text") or page.get("raw_text") or ""
            index.pages[p_no] = text
            lines = _line_offsets(text, page.get("line_boxes"))
            ids: List[str] = []
            for n, (s, e) in enumerate(split_sentence_spans(text), start=1):
                sid = f"p{p_no}.s{n}"
                sentence = Sentence(id=sid, page_number=p_no, index=n, start=s, end=e, text=text[s:e])
                for line in lines:
                    if line.start < e and line.end > s:
                        box = _box_for_span(line, s, e)
                        if box:
                            sentence.line_indexes.append(line.index)
                            sentence.boxes.append(box)
                index.sentences[sid] = sentence
                ids.append(sid)
            index.order[p_no] = ids
        return index

    def render_for_prompt(self) -> str:
        """The document as the model sees it: one `[pN.sM] text` line per sentence, per page."""
        blocks: List[str] = []
        for p_no in sorted(self.pages):
            lines = [f"--- START PAGE {p_no} ---"]
            for sid in self.order.get(p_no, []):
                flat = re.sub(r"\s+", " ", self.sentences[sid].text).strip()
                lines.append(f"[{sid}] {flat}")
            lines.append(f"--- END PAGE {p_no} ---")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _sort_key(sid: str) -> Tuple[int, int]:
        m = _ID_PATTERN.match(sid)
        return (int(m.group(1)), int(m.group(2))) if m else (10 ** 9, 10 ** 9)

    def resolve(self, ids: Any) -> QuoteSpan:
        """Turns sentence IDs into the exact page text. Any unknown ID fails the whole quote."""
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, (list, tuple)) or not ids:
            return QuoteSpan(ok=False, error="No sentence IDs were given for this quote.")

        clean: List[str] = []
        unknown: List[str] = []
        for raw in ids:
            sid = str(raw).strip().strip("[]").lower()
            if sid in self.sentences:
                if sid not in clean:
                    clean.append(sid)
            else:
                unknown.append(str(raw))
        if unknown:
            return QuoteSpan(
                ok=False,
                sentence_ids=clean,
                unknown_ids=unknown,
                error=f"Unknown sentence IDs: {', '.join(unknown)}. The quote was dropped.",
            )

        clean.sort(key=self._sort_key)
        # Group into runs of consecutive sentences on the same page.
        runs: List[List[Sentence]] = []
        for sid in clean:
            s = self.sentences[sid]
            if runs and runs[-1][-1].page_number == s.page_number and runs[-1][-1].index + 1 == s.index:
                runs[-1].append(s)
            else:
                runs.append([s])

        fragments: List[Dict[str, Any]] = []
        boxes: List[Dict[str, Any]] = []
        for run in runs:
            page_text = self.pages[run[0].page_number]
            fragments.append({
                "page_number": run[0].page_number,
                "text": page_text[run[0].start:run[-1].end],
                "sentence_ids": [s.id for s in run],
            })
        # One box per printed line. Two quoted sentences that share a line widen that line's box.
        by_line: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for sid in clean:
            s = self.sentences[sid]
            for line_idx, box in zip(s.line_indexes, s.boxes):
                key = (s.page_number, line_idx)
                held = by_line.get(key)
                if held is None:
                    held = {"page_number": s.page_number, "line_index": line_idx, "box_2d": list(box)}
                    by_line[key] = held
                    boxes.append(held)
                else:
                    old = held["box_2d"]
                    held["box_2d"] = [min(old[0], box[0]), min(old[1], box[1]), max(old[2], box[2]), max(old[3], box[3])]

        quote = " … ".join(f["text"] for f in fragments)
        return QuoteSpan(
            ok=True,
            quote=quote,
            page_number=fragments[0]["page_number"],
            sentence_ids=clean,
            fragments=fragments,
            boxes=boxes,
        )


# Which text field each item type keeps its quote in (the names the rest of the app reads).
QUOTE_FIELDS = {
    "provisions": "verbatim_text",
    "obligations": "verbatim_quote",
    "relationships": "supporting_quote",
}


def apply_quote_ids(payload: Dict[str, Any], index: SentenceIndex) -> List[Dict[str, Any]]:
    """Replaces each item's `quote_span_ids` with the exact quoted text, in place.

    Anything the model typed into a quote field is thrown away; only text copied from the IDs
    is kept. An item with missing or unknown IDs gets an empty quote and `needs_human_review`.
    Returns a list of problems found.
    """
    problems: List[Dict[str, Any]] = []
    for section, quote_field in QUOTE_FIELDS.items():
        items = payload.get(section)
        if not isinstance(items, list):
            payload[section] = []
            continue
        kept = []
        for item in items:
            if not isinstance(item, dict):
                continue
            span = index.resolve(item.get("quote_span_ids"))
            item[quote_field] = span.quote if span.ok else ""
            item["quote_span_ids"] = span.sentence_ids
            item["quote_fragments"] = span.fragments
            item["quote_boxes"] = span.boxes
            item["needs_human_review"] = not span.ok
            if span.ok:
                item["page_number"] = span.page_number
                item.pop("quote_error", None)
            else:
                item["quote_error"] = span.error
                item["unknown_quote_ids"] = span.unknown_ids
                problems.append({"item_type": section, "error": span.error, "unknown_ids": span.unknown_ids})
            kept.append(item)
        payload[section] = kept
    return problems
