"""Second reading of quoted sentences on pages that were read from their image (spec section 7).

`ensure_reading_checks` records what must be checked: one row per evidence sentence, `WAITING` when the
sentence is on a page read from its image, `NOT_NEEDED` for text-layer pages and pages a person
corrected. Claims on image-read pages stay `CHECKING` (hidden) until the rows have an answer.

`check_page` gives the answer, one page at a time: the lines of each quoted sentence are cut out of the
page image and read again, copied strictly; the two readings are compared with `same_reading`; a
disagreement gets a third, sharper reading. It runs only in the background job
(`claims/reading_jobs.py`), never inside a web request.
"""
import asyncio
import difflib
import hashlib
import io
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.core.config import settings
from backend.app.modules.claims import wording as W

from sqlalchemy import select

from backend.app.modules.analysis.sentences import SentenceIndex
from backend.app.modules.claims.checks import IMAGE_READ_METHODS, all_evidence_ids, CheckContext, PageInfo, _page_of
from backend.app.modules.claims.models import QuoteReadingCheck


def page_text_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def needs_reading(page: Any) -> bool:
    return (page.extraction_method or "") in IMAGE_READ_METHODS and not page.is_human_corrected


def _our_text(page: Any, sentence: Any) -> str:
    lines = page.line_boxes if isinstance(page.line_boxes, list) else []
    picked: List[str] = []
    for i in sentence.line_indexes:
        if 0 <= i < len(lines) and isinstance(lines[i], dict) and lines[i].get("text"):
            picked.append(str(lines[i]["text"]))
    return "\n".join(picked) if picked else sentence.text


async def ensure_reading_checks(db, claims: Iterable[Any], index: SentenceIndex, pages: Iterable[Any]) -> Dict[str, str]:
    """Adds a row for every evidence sentence that has none yet. Returns sentence ID -> status."""
    by_number = {p.page_number: p for p in pages}
    wanted: Dict[Tuple[Any, str, str], Any] = {}
    for claim in claims:
        for sid in all_evidence_ids(claim, CheckContext(index=index)):
            page = by_number.get(_page_of(sid))
            sentence = index.sentences.get(sid)
            if page is None or sentence is None:
                continue
            sha = page_text_sha(index.pages.get(page.page_number, ""))
            wanted.setdefault((page.id, sid, sha), (page, sentence))
    if not wanted:
        return {}

    page_ids = {key[0] for key in wanted}
    existing = (
        await db.execute(select(QuoteReadingCheck).where(QuoteReadingCheck.page_id.in_(page_ids)))
    ).scalars().all()
    rows = {(r.page_id, r.sentence_id, r.page_text_sha): r for r in existing}

    statuses: Dict[str, str] = {}
    for key, (page, sentence) in wanted.items():
        row = rows.get(key)
        if row is None:
            row = QuoteReadingCheck(
                page_id=page.id,
                sentence_id=sentence.id,
                line_indexes=list(sentence.line_indexes),
                page_text_sha=key[2],
                status="WAITING" if needs_reading(page) else "NOT_NEEDED",
                our_text=_our_text(page, sentence),
                reads=[],
                numbers_confirmed=[],
                attempts=0,
            )
            db.add(row)
            rows[key] = row
        elif row.status == "WAITING" and not needs_reading(page):
            row.status = "NOT_NEEDED"
        statuses[sentence.id] = row.status
    await db.flush()
    return statuses


# ---------------------------------------------------------------------------
# Second reading (spec section 7)
# ---------------------------------------------------------------------------
ILLEGIBLE = "[illegible]"

STRICT_PROMPT = (
    "You are given {n} image(s), numbered 1 to {n} in the order sent. Each one shows some printed lines "
    "of a Bangladesh Bank document.\n"
    "- Copy every line exactly as printed, in its original script (Bangla or English), one entry per "
    "printed line, from top to bottom.\n"
    "- Do not correct spelling, grammar or numbers. Do not translate, summarise or add anything.\n"
    "- Keep Bangla digits as Bangla digits.\n"
    "- Write [illegible] for anything you cannot read.\n"
    'Answer only with JSON: {{"crops": [{{"index": 1, "lines": ["..."]}}]}} with one entry per image, '
    "numbered as above."
)

READING_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "crops": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "index": {"type": "INTEGER"},
                    "lines": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["index", "lines"],
            },
        }
    },
    "required": ["crops"],
}

# Margin above and below the lines (0-1000 scale). The line boxes come from a model reading of the page and are
# often off by a line or two, so the strip is cut about three lines wider and focus_reading() then keeps only
# the lines that answer to ours. (15 here, and 0 on the tie-break, cut many sentences off: 2026-11-24 review.)
CROP_PADDING = 40
SENTENCE_MATCH_FLOOR = 0.6  # the least text likeness for finding a sentence in a whole-page reading


def _strip_punctuation(text: str) -> str:
    kept = "".join(ch for ch in text if not unicodedata.category(ch).startswith(("P", "S")))
    return re.sub(r"\s+", " ", kept).strip()


def levenshtein(a: str, b: str) -> int:
    """Character edit distance (insert, delete, replace), two rows of memory."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


_REFERENCE_NUMBER = re.compile(r"(?:\bno\b\.?|নং)\s*[-:]?\s*(\d[\d/.\-]*\d|\d)")


def _reference_codes(text: str, codes: Iterable[str]) -> Counter:
    t = W.norm(text)
    out: Counter = Counter()
    for m in _REFERENCE_NUMBER.finditer(t):
        out["no:" + m.group(1).strip("./-")] += 1
    for code in codes:
        c = W.norm(code)
        if not c:
            continue
        n = len(re.findall(rf"(?<![\w]){re.escape(c)}(?![\w])", t))
        if n:
            out["code:" + c] += n
    return out


def _figures(text: str) -> Counter:
    """Numbers and dates written in a line, as one multiset (dates are kept apart from plain numbers)."""
    t = W.norm(text)
    out: Counter = Counter(W.numbers_in(t))
    for _s, _e, d in W.date_matches(t):
        out["date:" + d.isoformat()] += 1
    return out


def confirmed_figures(our_text: str, native_text: Optional[str]) -> List[str]:
    """Numbers (2 or more digits) and dates of our reading that also stand in the page's text layer.

    Legacy-font PDFs keep their digits as plain digits in the text layer, so these are certain.
    """
    if not native_text or not our_text:
        return []
    native_numbers = W.numbers_in(native_text)
    native_runs = set(re.findall(r"\d+", W.norm(native_text)))
    native_dates = {d for _s, _e, d in W.date_matches(W.norm(native_text))}
    found: List[str] = []
    for key in _figures(our_text):
        if key.startswith("date:"):
            if date.fromisoformat(key[5:]) in native_dates:
                found.append(key)
            continue
        digits = re.sub(r"\D", "", key)
        if len(digits) < 2:
            continue
        if key in native_numbers or digits in native_runs:
            found.append(key)
    return found


# Bangla spelling variants that two correct readings of the same print often differ in: the hasant that joins
# conjuncts (ইন্সট্রুমেন্ট / ইনস্ট্রুমেন্ট), short and long i and u (সরকারি / সরকারী, উল্লেখিত / উল্লিখিত keeps
# its e/i difference), khanda ta, and the danda against a full stop. Numbers, "no" words and reference codes
# are compared separately and exactly, so folding these never hides a change of meaning.
_SPELLING_FOLD = str.maketrans({"\u09cd": None, "\u09c0": "\u09bf", "\u09c2": "\u09c1", "\u09ce": "\u09a4", "\u0964": ".", "\u0965": "."})


_YA_PHALA = "\u09cd\u09af"  # ফাইনান্স / ফাইন্যান্স: printed and dropped freely


def fold_spelling(text: str) -> str:
    """norm() plus the Bangla spelling folds above, without punctuation: the text the edit share is measured on."""
    return _strip_punctuation(W.norm(text).replace(_YA_PHALA, "").translate(_SPELLING_FOLD))


# A paragraph number the strip catches at the start of the line ("২। আসন্ন ...", "3. The ...") while our sentence
# starts after it (the number is a sentence of its own). Dropped from a reading only when ours has none.
_LIST_NUMBER = re.compile(r"^\s*\(?[0-9০-৯]{1,2}\s*[।.)]\s+")
# Memo / file numbers (০৫.০০.০০০০.১৭৫.০৮.০০২০.২৫-২৮): readers drop or add zeros and whole zero groups. Such a code
# (2+ dots, 4+ groups) is compared by its non-zero digits in order. Amounts (১,০০,০০,০০০) have no dots and are
# never touched; every other figure is still compared exactly.
_MEMO_CODE = re.compile(r"[0-9০-৯]+(?:\s*[.,\-/]\s*[0-9০-৯]+){3,}")


def _tame_memo_codes(text: str) -> str:
    def squash(m: "re.Match[str]") -> str:
        code = m.group(0)
        if code.count(".") < 2:
            return code
        digits = re.sub(r"[^0-9]", "", code.translate(W._BANGLA_DIGITS)).replace("0", "")
        return f" {digits} "
    return _MEMO_CODE.sub(squash, text or "")


def _drop_list_number(ours: str, reading: str) -> str:
    if _LIST_NUMBER.match(reading or "") and not _LIST_NUMBER.match(ours or ""):
        return _LIST_NUMBER.sub("", reading, count=1)
    return reading or ""


def whole_word_gap(ca: str, cb: str, min_letters: int = 3) -> bool:
    """True when one folded reading has a whole word (3+ letters) the other lacks, not a respelling or a split."""
    wa, wb = ca.split(), cb.split()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "delete" and any(len(w) >= min_letters for w in wa[i1:i2]):
            return True
        if op == "insert" and any(len(w) >= min_letters for w in wb[j1:j2]):
            return True
    return False


WORD_CHANGE_EDITS = 3  # letters a word may not differ by and still be "the same word, spelled differently"


def different_word(ca: str, cb: str) -> bool:
    """True when a word was swapped for another (3+ letter edits between the pair), not respelled."""
    wa, wb = ca.split(), cb.split()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "replace" and (i2 - i1) == (j2 - j1):
            for x, y in zip(wa[i1:i2], wb[j1:j2]):
                if max(len(x), len(y)) <= 20 and not re.search(r"\d", x + y) and levenshtein(x, y) >= WORD_CHANGE_EDITS:
                    return True
    return False


def same_reading(
    a: str,
    b: str,
    confirmed: Iterable[str] = (),
    codes: Iterable[str] = (),
    max_share: Optional[float] = None,
) -> bool:
    """True when two readings of the same printed lines agree (spec 7.4). `a` is the reading being judged.

    Both must be free of "[illegible]", and carry the same numbers, dates, "no" words and reference codes.
    A figure of `a` that the text layer confirms counts as present in `b`: if `b` shows something else
    there, `b` is the one that is wrong. The rest must be within the allowed share of character edits.
    """
    if ILLEGIBLE in (a or "").lower() or ILLEGIBLE in (b or "").lower():
        return False
    share = settings.QUOTE_CHECK_MAX_EDIT_SHARE if max_share is None else max_share
    a, b = _tame_memo_codes(a), _tame_memo_codes(b)
    b = _drop_list_number(a, b)
    a = _drop_list_number(b, a)

    fa, fb = _figures(a), _figures(b)
    sure = [k for k in set(confirmed) if k in fa]
    # Figures of `a` the text layer confirms: if `b` shows something else in their place, `b` is the one that is wrong.
    budget = sum(fa[k] - min(fa[k], fb[k]) for k in sure)
    for k in sure:
        fb[k] = 0
        fa[k] = 0
    fa, fb = +fa, +fb
    matched_in_b = Counter({k: min(fa[k], fb[k]) for k in fa})
    if sum((fb - matched_in_b).values()) > budget:
        return False  # `b` has figures that `a` does not
    if fa - matched_in_b:
        return False  # `a` has figures that `b` lacks, and the text layer does not confirm them

    if W.count_words(a, W.NEGATION) != W.count_words(b, W.NEGATION):
        return False
    codes = list(codes)
    if _reference_codes(a, codes) != _reference_codes(b, codes):
        return False

    ca, cb = fold_spelling(a), fold_spelling(b)
    if not ca:
        return not cb
    if different_word(ca, cb):
        return False  # রেগুলেশন / রেজল্যুশন (Regulation / Resolution): a respelling never differs this much
    if not whole_word_gap(ca, cb) and levenshtein(ca, cb) / len(ca) <= share:
        return True
    # Header blocks (date, reference, addressee side by side) come back in another order: the same words,
    # figures and codes (checked above), only arranged differently, are the same reading.
    wa, wb = ca.split(), cb.split()
    if len(wa) >= 6 and abs(len(wa) - len(wb)) <= 1:
        sa, sb = " ".join(sorted(wa)), " ".join(sorted(wb))
        return levenshtein(sa, sb) / len(sa) <= share
    return False


# ----- self-correction: both readers agree, our text differs only in figures --------------------------------
_TO_BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_FIGURE = re.compile(r"(?<!\d)\d+(?:\.\d+)?(?!\d)")  # 177/2026-3058 gives 177, 2026, 3058
FIX_MIN_DIGITS = 2  # single digits (list numbers, "3 months") are never changed by a correction


def _ascii_digits(text: str) -> str:
    return (text or "").translate(W._BANGLA_DIGITS)


def figure_fixes(ours: str, agreed: str, confirmed: Iterable[str] = (), codes: Iterable[str] = ()) -> Optional[List[List[str]]]:
    """[[old, new], ...] when two agreeing readings differ from our text only in figures, else None.

    Safe by construction: the same count of figures on both sides; every changed figure has 2+ digits and is
    not confirmed by the PDF's text layer; one old figure never maps to two new ones; and our text with the
    readers' figures put in must then agree with the readers in everything else (words, "no" words, codes).
    """
    a, b = _ascii_digits(ours), _ascii_digits(agreed)
    na, nb = _FIGURE.findall(a), _FIGURE.findall(b)
    if not na or len(na) != len(nb):
        return None
    pairs = [(x, y) for x, y in zip(na, nb) if x != y]
    if not pairs:
        return None
    sure = {re.sub(r"\D", "", c) for c in confirmed if not str(c).startswith("date:")}
    mapping: Dict[str, str] = {}
    for x, y in pairs:
        digits = re.sub(r"\D", "", x)
        if len(digits.lstrip("0")) < FIX_MIN_DIGITS or digits in sure:  # "০৩" is a single digit
            return None
        if mapping.get(x, y) != y:
            return None
        mapping[x] = y
    # a figure kept unchanged elsewhere in the same text must not share an old value (it would be rewritten too)
    if any(x == old for x, y in zip(na, nb) if x == y for old in mapping):
        return None
    it = iter(nb)
    patched = _FIGURE.sub(lambda _m: next(it), a)
    if not same_reading(patched, b, (), codes):
        return None
    return [[x, y] for x, y in mapping.items()]


def apply_figure_fixes(text: Any, fixes: Iterable[Iterable[str]]) -> Any:
    """The text with each old figure replaced by the new one, in Latin and Bangla digits (whole figures only)."""
    if not isinstance(text, str) or not text:
        return text
    for old, new in fixes:
        for o, n in ((old, new), (old.translate(_TO_BANGLA_DIGITS), new.translate(_TO_BANGLA_DIGITS))):
            text = re.sub(rf"(?<![\d০-৯]){re.escape(o)}(?![\d০-৯])", n, text)
    return text


def fixes_of(row: Any) -> List[List[str]]:
    """The figure fixes stored on a CORRECTED reading row."""
    for item in reversed(list(row.reads or [])):
        if isinstance(item, dict) and item.get("kind") == "AGREED" and isinstance(item.get("fixes"), list):
            return [list(p) for p in item["fixes"] if isinstance(p, (list, tuple)) and len(p) == 2]
    return []


# ----- cropping and the call -------------------------------------------------
def union_box(page: Any, line_indexes: List[int]) -> Optional[List[int]]:
    """The union of the lines' boxes ([ymin, xmin, ymax, xmax], 0-1000), or None when a line has no box."""
    lines = page.line_boxes if isinstance(page.line_boxes, list) else []
    boxes: List[List[int]] = []
    for i in line_indexes or []:
        box = lines[i].get("box_2d") if 0 <= i < len(lines) and isinstance(lines[i], dict) else None
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            return None
        try:
            boxes.append([int(v) for v in box])
        except (TypeError, ValueError):
            return None
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def crop_png(page_png: bytes, box: List[int], pad: int = 0) -> bytes:
    """A strip of the page image: the box's lines plus `pad` above and below, over the full page width."""
    from PIL import Image

    with Image.open(io.BytesIO(page_png)) as img:
        w, h = img.size
        top = max(0, box[0] - pad)
        bottom = min(1000, box[2] + pad)
        y0 = int(h * top / 1000)
        y1 = max(y0 + 1, int(round(h * bottom / 1000)))
        out = io.BytesIO()
        img.crop((0, y0, w, min(h, y1))).save(out, format="PNG")
        return out.getvalue()


async def send_images(images: List[bytes], model: str, prompt: Optional[str] = None):
    """One call that reads several strips at once (reuses the key rotation, gates and quota marks of the page reader)."""
    from backend.app.modules.extraction import vision

    return await vision.read_images_json(
        images, (prompt or STRICT_PROMPT).format(n=len(images)), READING_SCHEMA, model=model
    )


def _texts_from_reply(data: Any, count: int) -> List[Optional[str]]:
    """The text of each crop, by its number; None for any crop the answer left out."""
    out: List[Optional[str]] = [None] * count
    crops = data.get("crops") if isinstance(data, dict) else None
    if not isinstance(crops, list):
        return out
    positional = len(crops) == count
    for pos, item in enumerate(crops):
        if not isinstance(item, dict) or not isinstance(item.get("lines"), list):
            continue
        n = item.get("index")
        slot = n - 1 if isinstance(n, int) and 1 <= n <= count else (pos if positional else None)
        if slot is None or out[slot] is not None:
            continue
        lines = [str(x).rstrip() for x in item["lines"] if str(x).strip()]
        out[slot] = "\n".join(lines)
    return out


def locate_in_page_reading(our_text: str, page_reading: str) -> Optional[str]:
    """The lines of a whole-page reading that best match our lines (a window of about the same length), or None."""
    ours = W.norm(our_text)
    lines = [ln for ln in page_reading.split("\n") if ln.strip()]
    if not ours or not lines:
        return None
    best, best_score = None, 0.0
    low, high = len(ours) * 0.8, len(ours) * 1.2
    for i in range(len(lines)):
        joined = ""
        for j in range(i, len(lines)):
            joined = lines[j] if j == i else joined + "\n" + lines[j]
            size = len(W.norm(joined))
            if size > high and j > i:
                break
            if size < low:
                continue
            matcher = difflib.SequenceMatcher(None, ours, W.norm(joined), autojunk=False)
            if matcher.real_quick_ratio() < best_score or matcher.quick_ratio() < best_score:
                continue
            score = matcher.ratio()
            if score > best_score:
                best, best_score = joined, score
    return best if best is not None and best_score >= SENTENCE_MATCH_FLOOR else None


def _real_failure(row: Any, error: str, summary: Dict[str, int]) -> None:
    row.attempts = (row.attempts or 0) + 1
    row.last_error = (error or "no answer")[:500]
    summary["failed"] += 1
    if row.attempts >= settings.QUOTE_CHECK_MAX_ATTEMPTS:
        _finish(row, "UNCLEAR", summary)


def _finish(row: Any, status: str, summary: Dict[str, int]) -> None:
    row.status = status
    row.checked_at = datetime.now(timezone.utc)
    if status != "UNCLEAR":
        row.last_error = None
    summary["checked"] += 1
    summary[status.lower()] += 1


def focus_reading(our_text: str, text: str) -> str:
    """The lines of a strip reading that answer to our lines.

    A strip is cut with some space above and below, and a box can touch a neighbouring line, so the
    second reading may carry a line or two that were never ours. Those are cut off before the two
    readings are compared. When no run of lines looks like ours, the whole reading is kept (and then
    disagrees, which is the safe answer).
    """
    found = locate_in_page_reading(our_text, text)
    return found if found is not None else text


def _add_read(row: Any, kind: str, text: str, model: str) -> str:
    """Stores a reading and returns the part of it that is compared with ours."""
    focused = focus_reading(row.our_text or "", text) if kind != "PAGE" else text
    item: Dict[str, Any] = {"kind": kind, "text": focused, "model": model}
    if focused != text:
        item["full"] = text
    row.reads = list(row.reads or []) + [item]
    return focused


def _chunks(items: List[Any], size: int) -> List[List[Any]]:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _call(send: Any, images: List[bytes], model: str, summary: Dict[str, Any]):
    result = await send(images, model)
    if not getattr(result, "not_sent", False):
        summary["calls"] += 1
    return result


def _stop_reason(result: Any, summary: Dict[str, Any]) -> bool:
    """True when the whole job should stop: no key, out of quota or the service is busy (nothing is counted)."""
    if getattr(result, "no_key", False):
        summary["no_key"] = True
        summary["stop"] = True
        return True
    if getattr(result, "quota_exhausted", False):
        summary["out_of_quota"] = True
        summary["stop"] = True
        return True
    if getattr(result, "transient", False):
        summary["waiting_busy"] += 1
        summary["stop"] = True
        return True
    return False


async def check_page(page: Any, rows: List[Any], pdf_bytes: bytes, send: Any, codes: Iterable[str] = ()) -> Dict[str, Any]:
    """Judges every waiting row of one page. Returns counts; also `out_of_quota`, `no_key`, `stop` when the job should stop."""
    summary: Dict[str, Any] = {
        "checked": 0, "clean": 0, "misread": 0, "unclear": 0, "corrected": 0, "not_needed": 0, "failed": 0, "calls": 0,
        "waiting_busy": 0,
    }
    current_sha = page_text_sha(page.cleaned_text or page.raw_text or "")
    todo: List[Any] = []
    for row in rows:
        if row.status != "WAITING":
            continue
        if not needs_reading(page):
            row.status = "NOT_NEEDED"
            summary["not_needed"] += 1
        elif row.page_text_sha != current_sha:
            row.status = "NOT_NEEDED"  # the page text changed; the sentence has new rows
            summary["not_needed"] += 1
        else:
            todo.append(row)
    if not todo:
        return summary

    if not pdf_bytes:
        for row in todo:
            _real_failure(row, "The page file could not be opened.", summary)
        return summary

    from backend.app.modules.extraction import vision

    confirmed = {id(r): confirmed_figures(r.our_text or "", page.native_text) for r in todo}
    for r in todo:
        r.numbers_confirmed = list(confirmed[id(r)])
    boxed: List[Tuple[Any, List[int]]] = []
    unboxed: List[Any] = []
    for row in todo:
        box = union_box(page, list(row.line_indexes or []))
        (boxed.append((row, box)) if box else unboxed.append(row))

    pngs: Dict[int, bytes] = {}

    def page_png(dpi: int) -> bytes:
        if dpi not in pngs:
            pngs[dpi] = vision.render_page_png(pdf_bytes, page.page_number, dpi=dpi)
        return pngs[dpi]

    def judge(row: Any, text: str) -> bool:
        return same_reading(row.our_text or "", text, confirmed[id(row)], codes)

    # --- first reading: crops of the lines, then whole page for rows without boxes -------------
    first = [(r, b) for r, b in boxed if not (r.reads or [])]
    missed: List[Any] = []
    for group in _chunks(first, settings.QUOTE_CHECK_CROPS_PER_CALL):
        try:
            images = await asyncio.to_thread(
                lambda g=group: [crop_png(page_png(settings.QUOTE_CHECK_DPI), b, CROP_PADDING) for _r, b in g]
            )
        except Exception as e:
            for r, _b in group:
                _real_failure(r, f"crop failed: {type(e).__name__}", summary)
            continue
        result = await _call(send, images, settings.QUOTE_CHECK_MODEL, summary)
        if not result.success:
            if _stop_reason(result, summary):
                return summary
            for r, _b in group:
                _real_failure(r, result.error or "no answer", summary)
            continue
        for (r, _b), text in zip(group, _texts_from_reply(result.data, len(group))):
            if text is None:
                _real_failure(r, "The reading of this strip was left out of the answer.", summary)
                continue
            if locate_in_page_reading(r.our_text or "", text) is None:
                # The strip holds other lines (the line box was off): not evidence about our text. Read the page.
                _add_read(r, "CROP_MISS", text, result.model or settings.QUOTE_CHECK_MODEL)
                missed.append(r)
                continue
            if judge(r, _add_read(r, "CROP", text, result.model or settings.QUOTE_CHECK_MODEL)):
                _finish(r, "CLEAN", summary)

    whole = [r for r in unboxed if not (r.reads or [])]
    if whole:
        try:
            image = await asyncio.to_thread(page_png, settings.QUOTE_CHECK_DPI)
        except Exception as e:
            for r in whole:
                _real_failure(r, f"render failed: {type(e).__name__}", summary)
            whole = []
    if whole:
        result = await _call(send, [image], settings.QUOTE_CHECK_MODEL, summary)
        if not result.success:
            if _stop_reason(result, summary):
                return summary
            for r in whole:
                _real_failure(r, result.error or "no answer", summary)
        else:
            reading = (_texts_from_reply(result.data, 1) or [None])[0]
            for r in whole:
                if reading is None:
                    _real_failure(r, "The whole-page reading was left out of the answer.", summary)
                    continue
                found = locate_in_page_reading(r.our_text or "", reading)
                if found is None:
                    _add_read(r, "PAGE", "", result.model or settings.QUOTE_CHECK_MODEL)
                    _finish(r, "UNCLEAR", summary)
                    continue
                _add_read(r, "PAGE", found, result.model or settings.QUOTE_CHECK_MODEL)
                _finish(r, "CLEAN" if judge(r, found) else "UNCLEAR", summary)

    # --- tie-break for the rows whose first reading disagreed ---------------------------------
    second = [
        (r, b) for r, b in boxed
        if r.status == "WAITING" and len(r.reads or []) == 1 and (r.reads[0] or {}).get("kind") == "CROP"
    ]
    for group in _chunks(second, settings.QUOTE_CHECK_CROPS_PER_CALL):
        try:
            images = await asyncio.to_thread(
                lambda g=group: [crop_png(page_png(settings.QUOTE_TIEBREAK_DPI), b, CROP_PADDING) for _r, b in g]
            )
        except Exception as e:
            for r, _b in group:
                _real_failure(r, f"crop failed: {type(e).__name__}", summary)
            continue
        result = await _call(send, images, settings.QUOTE_TIEBREAK_MODEL, summary)
        if not result.success:
            if _stop_reason(result, summary):
                return summary
            for r, _b in group:
                _real_failure(r, result.error or "no answer", summary)
            continue
        for (r, _b), text in zip(group, _texts_from_reply(result.data, len(group))):
            if text is None:
                _real_failure(r, "The reading of this strip was left out of the answer.", summary)
                continue
            if locate_in_page_reading(r.our_text or "", text) is None:
                _add_read(r, "CROP_MISS", text, result.model or settings.QUOTE_TIEBREAK_MODEL)
                missed.append(r)
                continue
            text = _add_read(r, "SHARP_CROP", text, result.model or settings.QUOTE_TIEBREAK_MODEL)
            first_text = (r.reads[0] or {}).get("text", "")
            if judge(r, text):
                _finish(r, "CLEAN", summary)
            elif same_reading(first_text, text, (), codes):
                # Two independent readings agree and ours differs. When the difference is only in figures our
                # text layer does not confirm, ours is the wrong one: correct it instead of hiding the point.
                fixes = figure_fixes(r.our_text or "", first_text, confirmed[id(r)], codes)
                if fixes:
                    r.reads = list(r.reads or []) + [{"kind": "AGREED", "text": first_text, "fixes": fixes}]
                    _finish(r, "CORRECTED", summary)
                else:
                    _finish(r, "MISREAD", summary)
            else:
                _finish(r, "UNCLEAR", summary)

    # --- crop misses: read the whole page once and find our lines in it ---------------------------
    retry = [r for r in missed if r.status == "WAITING" and not any((x or {}).get("kind") == "PAGE" for x in (r.reads or []))]
    if retry:
        try:
            image = await asyncio.to_thread(page_png, settings.QUOTE_CHECK_DPI)
        except Exception as e:
            for r in retry:
                _real_failure(r, f"render failed: {type(e).__name__}", summary)
            return summary
        result = await _call(send, [image], settings.QUOTE_CHECK_MODEL, summary)
        if not result.success:
            if _stop_reason(result, summary):
                return summary
            for r in retry:
                _real_failure(r, result.error or "no answer", summary)
            return summary
        reading = (_texts_from_reply(result.data, 1) or [None])[0]
        for r in retry:
            found = locate_in_page_reading(r.our_text or "", reading or "")
            if found is None:
                _add_read(r, "PAGE", "", result.model or settings.QUOTE_CHECK_MODEL)
                _finish(r, "UNCLEAR", summary)
                continue
            _add_read(r, "PAGE", found, result.model or settings.QUOTE_CHECK_MODEL)
            _finish(r, "CLEAN" if judge(r, found) else "UNCLEAR", summary)
    return summary


def rejudge(row: Any, codes: Iterable[str] = ()) -> Optional[str]:
    """The status the readings already stored on a row give under today's comparison rules, or None to leave it.

    No new reading is made. Used after the rules change (owner, 2026-11-28: Bangla spelling variants, paragraph
    numbers, header order and memo-number zeros were counted as misreadings). The order follows check_page: the
    first reading decides; a disagreeing first reading is settled by the sharper second one; two agreeing readings
    that differ from ours only in figures correct our figures.
    """
    reads = [x for x in (row.reads or []) if isinstance(x, dict)]
    by_kind: Dict[str, str] = {}
    for x in reads:
        by_kind.setdefault(x.get("kind") or "", x.get("text") or "")
    confirmed = list(row.numbers_confirmed or [])
    ours = row.our_text or ""

    def judge(text: str) -> bool:
        return bool(text) and same_reading(ours, text, confirmed, codes)

    for kind in ("CROP", "PAGE"):
        if kind in by_kind and judge(by_kind[kind]):
            return "CLEAN"
    if "SHARP_CROP" in by_kind:
        sharp, first = by_kind["SHARP_CROP"], by_kind.get("CROP", "")
        if judge(sharp):
            return "CLEAN"
        if first and same_reading(first, sharp, (), codes):
            fixes = figure_fixes(ours, first, confirmed, codes)
            if fixes:
                row.reads = list(row.reads or []) + [{"kind": "AGREED", "text": first, "fixes": fixes}]
                return "CORRECTED"
            return "MISREAD"
        return "UNCLEAR"
    return None

