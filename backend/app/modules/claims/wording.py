"""Plain text helpers and word lists for the claim checks (docs/specs/CLAIM_CHECKS_SPEC.md section 3.2 and 3.4).

All word lists live in this one file, as tuples, so they can be tuned later on the dev split only.
Everything here is plain code: no network, no model.
"""
import re
import unicodedata
from collections import Counter
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
})


def norm(text: Optional[str]) -> str:
    """NFC, no zero-width joiners, Bangla digits as 0-9, lower case, plain quotes and dashes, one space."""
    if not text:
        return ""
    s = unicodedata.normalize("NFC", str(text))
    s = s.replace("‌", "").replace("‍", "")
    s = s.translate(_BANGLA_DIGITS).translate(_QUOTES).lower()
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Word lists (English and Bangla)
# ---------------------------------------------------------------------------
NEGATION: Tuple[str, ...] = (
    "not", "no", "never", "shall not", "must not", "may not", "cannot", "prohibited", "forbidden", "barred", "refrain",
    "না", "নয়", "নহে", "নেই", "নাই", "যাবে না", "পারবে না", "নিষিদ্ধ", "বিরত",
)

# Words that mean "no" and can follow a permission word ("may not", "পারবে না").
NEGATION_TOKENS: Tuple[str, ...] = ("not", "no", "never", "cannot", "না", "নয়", "নহে", "নেই", "নাই")

# A strong prohibition: a point that says "must be done" cannot rest on a quote that says this.
STRONG_PROHIBITION: Tuple[str, ...] = ("shall not", "must not", "prohibited", "যাবে না", "নিষিদ্ধ")

DUTY_WORDS: Dict[str, Tuple[str, ...]] = {
    "MANDATORY": ("shall", "must", "required", "have to", "ensure", "ensuring",
                  # Bangladesh Bank gives orders as "advice": "Banks are advised to ...", "... পরামর্শ প্রদান করা যাচ্ছে".
                  "advised to", "are advised", "is advised", "requested to",
                  # Mined from 11,264 archive pages (dev and test circulars left out), 14 Nov 2026:
                  "instructed to", "directed to", "obliged to",
                  "করতে হবে", "হবে", "হবেন", "করবে", "করিবে", "থাকবে", "বাধ্যতামূলক", "নিশ্চিত", "আবশ্যক",
                  "পরামর্শ প্রদান করা যাচ্ছে", "অনুরোধ করা যাচ্ছে",
                  # "You are instructed to follow ...", "... shall be followed" (manual archive analysis, 14 Nov 2026).
                  "নির্দেশনা প্রদান করা হলো", "নির্দেশনা প্রদান করা হল", "নির্দেশ প্রদান করা হলো", "নির্দেশনা দেয়া হলো",
                  "নির্দেশনা দেওয়া হলো", "অনুসরণীয়", "পরিপালনীয়",
                  # Old (sadhu) Bangla used in older circulars.
                  "হইবে", "করিতে হইবে", "থাকিবে"),
    "PROHIBITION": NEGATION,
    "PERMISSION": ("may", "allowed", "permitted", "can", "entitled to", "পারবে", "পারবেন", "পারে", "অনুমতি",
                   "যাবে", "পারিবে", "যাইবে"),
    "REPORTING": ("submit", "submission", "report", "send", "furnish", "forward", "communicate", "সরবরাহ", "প্রেরণ", "দাখিল", "পাঠাতে", "রিপোর্ট", "অবহিত",
                  # An application to Bangladesh Bank with documents is a submission.
                  "apply", "আবেদন"),
    "APPROVAL": ("approval", "approve", "prior permission", "consent", "অনুমোদন", "অনুমতি", "সম্মতি"),
    "RECORD_RETENTION": ("preserve", "maintain", "retain", "keep", "সংরক্ষণ"),
    "DISCLOSURE": ("disclose", "publish", "display", "inform", "প্রকাশ", "প্রদর্শন", "তথ্য প্রদান", "অবহিত"),
    "CONDITIONAL": ("if", "where", "in case", "provided", "subject to", "unless", "only after",
                    "যদি", "ক্ষেত্রে", "শর্তে", "সাপেক্ষে"),
    "RECOMMENDATION": ("should", "encouraged", "advised", "উৎসাহিত", "পরামর্শ"),
}

CHANGE_WORDS: Dict[str, Tuple[str, ...]] = {
    "AMENDS": ("amend", "amendment", "modified", "modify", "revised", "revise", "substituted", "substitute", "inserted", "insert",
               "deleted", "delete",
               "সংশোধন", "সংশোধিত", "পরিবর্তন", "সংযোজন", "প্রতিস্থাপ"),
    "REPEALS": ("repeal", "rescind", "revoked", "revoke", "withdrawn", "withdraw", "cancelled", "cancel", "ceases to have effect",
                "রহিত", "বাতিল", "প্রত্যাহার"),
    "SUPERSEDES": ("supersede", "in supersession of", "replace", "in place of", "প্রতিস্থাপন", "পরিবর্তে", "স্থলে"),
    "REPLACES": ("supersede", "in supersession of", "replace", "in place of", "প্রতিস্থাপন", "পরিবর্তে", "স্থলে"),
}

EXEMPT_WORDS: Tuple[str, ...] = (
    "except", "exempt", "not applicable", "shall not apply", "excluding",
    "ব্যতীত", "ছাড়া", "প্রযোজ্য নয়", "অব্যাহতি",
)

CLARIFY_WORDS: Tuple[str, ...] = ("clarify", "clarifies", "clarified", "clarification", "স্পষ্টীকরণ", "ব্যাখ্যা")

IMMEDIATE_EFFECT: Tuple[str, ...] = (
    "with immediate effect", "immediately", "from the date of issue",
    "অবিলম্বে", "অনতিবিলম্বে", "জারির তারিখ হতে", "তাৎক্ষণিকভাবে",
)

CHANGE_TYPES: Tuple[str, ...] = ("AMENDS", "REPEALS", "SUPERSEDES", "REPLACES")

NUMBER_WORDS: Dict[str, str] = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
    "forty-five": "45", "forty five": "45", "sixty": "60", "ninety": "90", "hundred": "100",
}

# ---------------------------------------------------------------------------
# Entities (section 3.4): canonical name -> aliases (English and Bangla)
# ---------------------------------------------------------------------------
ENTITIES: Dict[str, Tuple[str, ...]] = {
    "SCHEDULED_BANK": ("scheduled bank", "scheduled banks", "scheduled commercial bank", "scheduled commercial banks",
                       "all banks", "তফসিলি ব্যাংক", "তফসিলী ব্যাংক", "তফসিলভুক্ত ব্যাংক",
                       # "bank company" is the Bank Company Act's word for a scheduled bank; "তফসিল ব্যাংক" is a common misreading.
                       "bank company", "bank companies", "ব্যাংক কোম্পানী", "ব্যাংক-কোম্পানী", "ব্যাংক কোম্পানি", "ব্যাংক-কোম্পানি",
                       "তফসিল ব্যাংক"),
    "STATE_OWNED_BANK": ("state-owned commercial bank", "state owned commercial bank", "state-owned bank", "state owned bank",
                         "state-owned banks", "state owned banks", "রাষ্ট্রায়ত্ত"),
    "PRIVATE_COMMERCIAL_BANK": ("private commercial bank", "private commercial banks", "private bank", "private banks",
                                "বেসরকারি বাণিজ্যিক ব্যাংক", "বেসরকারি ব্যাংক"),
    "ISLAMIC_BANK": ("islamic shariah", "islamic bank", "islamic banks", "islamic banking", "shariah based",
                     "ইসলামী শরীআহ", "ইসলামী শরিয়াহ", "ইসলামী ব্যাংক"),
    "FOREIGN_BANK": ("foreign bank", "foreign banks", "foreign commercial bank", "foreign commercial banks", "বিদেশী ব্যাংক", "বিদেশি ব্যাংক"),
    "SPECIALIZED_BANK": ("specialized bank", "specialised bank", "specialized banks", "specialised banks", "বিশেষায়িত ব্যাংক"),
    "NBFI": ("non-bank financial institution", "non-bank financial institutions", "non bank financial institution",
             "non bank financial institutions", "nbfi", "nbfis", "financial institution", "financial institutions", "আর্থিক প্রতিষ্ঠান",
             "finance company", "finance companies", "ফাইন্যান্স কোম্পানি", "ফাইন্যান্স কোম্পানী", "ফাইনান্স কোম্পানি"),
    "AUTHORIZED_DEALER": ("authorized dealer", "authorised dealer", "authorized dealers", "authorised dealers", "ad branch",
                          "ad branches", "অনুমোদিত ডিলার", "অথরাইজড ডিলার"),
    "MONEY_CHANGER": ("money changer", "money changers", "moneychanger", "মানি চেঞ্জার", "মানিচেঞ্জার"),
    "PAYMENT_SERVICE_PROVIDER": ("payment service provider", "payment service providers", "psp", "psps", "pso", "psos",
                                 "payment system operator", "payment system operators", "পেমেন্ট সেবা প্রদানকারী",
                                 "পেমেন্ট সার্ভিস প্রোভাইডার", "পেমেন্ট সিস্টেম অপারেটর"),
    "MOBILE_FINANCIAL_SERVICE": ("mobile financial service", "mobile financial services", "mfs", "মোবাইল আর্থিক সেবা",
                                 "মোবাইল ফিন্যান্সিয়াল সার্ভিস", "মোবাইল ফাইনান্সিয়াল সার্ভিস", "মোবাইল ফাইন্যান্সিয়াল সার্ভিস", "এমএফএস"),
    "MICROFINANCE_INSTITUTION": ("microfinance institution", "microfinance institutions", "micro-finance institution",
                                 "mfi", "mfis", "ক্ষুদ্রঋণ", "microcredit", "মাইক্রোক্রেডিট"),
    "EXCHANGE_HOUSE": ("exchange house", "exchange houses", "এক্সচেঞ্জ হাউজ", "এক্সচেঞ্জ হাউস"),
    "OFFSHORE_BANKING_UNIT": ("offshore banking unit", "offshore banking units", "obu", "obus", "অফশোর ব্যাংকিং ইউনিট",
                              "অফশোর ব্যাংকিং"),
}

# Old values from the first analysis format.
LEGACY_ENTITY_NAMES: Dict[str, str] = {
    "SCHEDULED_COMMERCIAL_BANK": "SCHEDULED_BANK",
    "COMMERCIAL_BANK": "SCHEDULED_BANK",
    "PAYMENT_SERVICE_OPERATOR": "PAYMENT_SERVICE_PROVIDER",
}

# Kinds of scheduled bank: a circular to "all scheduled banks" also covers them.
SCHEDULED_BANK_KINDS: Tuple[str, ...] = (
    "STATE_OWNED_BANK", "PRIVATE_COMMERCIAL_BANK", "ISLAMIC_BANK", "FOREIGN_BANK", "SPECIALIZED_BANK",
)

# Caps: an upper limit is a "must not" (the answer key and prompt v4 call "shall not exceed" a prohibition).
# Floors ("at least", "ন্যূনতম") are positive duties, not prohibitions.
CAP_WORDS: Tuple[str, ...] = (
    "maximum", "at most", "not exceed", "exceed", "ceiling", "within the limit",
    "সর্বোচ্চ", "অধিক হবে না", "অতিক্রম", "সীমার মধ্যে", "মধ্যে থাকতে",
)

# "Only if": a rule that allows something only under a condition forbids it otherwise (a must not).
ONLY_WORDS: Tuple[str, ...] = (
    "only provided", "only if", "only when", "only after", "only upon", "only against", "only for",
    "শুধুমাত্র", "কেবলমাত্র", "শুধু", "কেবল",
)

# The greeting that ends the address block of a letter.
GREETINGS: Tuple[str, ...] = ("dear sir", "dear madam", "dear sirs", "প্রিয় মহোদয়", "জনাব")

ADDRESSEE_ALL_SCHEDULED: Tuple[str, ...] = (
    "all scheduled banks", "all scheduled commercial banks", "সকল তফসিলি ব্যাংক", "সকল তফসিলী ব্যাংক", "সব তফসিলি ব্যাংক",
)

# ---------------------------------------------------------------------------
# Matching words in text
# ---------------------------------------------------------------------------
_BANGLA = "ঀ-৿"
_ENGLISH_ENDINGS = r"(?:s|es|d|ed|ing)?"
_pattern_cache: Dict[Tuple[str, str], "re.Pattern[str]"] = {}


def _is_bangla(word: str) -> bool:
    return any("ঀ" <= ch <= "৿" for ch in word)


def _word_pattern(word: str, mode: str) -> "re.Pattern[str]":
    """mode "whole": a whole word (English words may carry s, es, d, ed, ing).
    mode "stem": the word starts a word ("amend" finds "amended" and "amendment")."""
    key = (word, mode)
    cached = _pattern_cache.get(key)
    if cached is not None:
        return cached
    w = re.escape(norm(word)).replace(r"\ ", r"\s+")
    if _is_bangla(word):
        start = rf"(?<![{_BANGLA}])"
        # Short Bangla words (না, হবে) must be whole tokens; longer ones may carry endings.
        short = len(norm(word).replace(" ", "")) <= 4
        end = rf"(?![{_BANGLA}])" if (mode == "whole" and short) else ""
        pat = re.compile(start + w + end)
    else:
        start = r"(?<![a-z0-9])"
        if mode == "stem":
            pat = re.compile(start + w)
        else:
            pat = re.compile(start + w + _ENGLISH_ENDINGS + r"(?![a-z0-9])")
    _pattern_cache[key] = pat
    return pat


def find_words(text: str, words: Iterable[str], mode: str = "whole") -> List["re.Match[str]"]:
    """All matches of any of the words in the (already normalised or raw) text, in order."""
    t = norm(text)
    out: List["re.Match[str]"] = []
    for w in words:
        out.extend(_word_pattern(w, mode).finditer(t))
    out.sort(key=lambda m: m.start())
    return out


def has_any(text: str, words: Iterable[str], mode: str = "whole") -> bool:
    return bool(find_words(text, words, mode))


def count_words(text: str, words: Iterable[str], mode: str = "whole") -> Counter:
    """How many times each word occurs. Used to compare two readings of the same line."""
    t = norm(text)
    c: Counter = Counter()
    for w in words:
        n = len(_word_pattern(w, mode).findall(t))
        if n:
            c[norm(w)] += n
    return c


def _tokens(text: str) -> List[str]:
    return [tok for tok in re.split(r"[\s,;:.()\[\]\"'।॥]+", text) if tok]


def has_permission_word(text: str) -> bool:
    """A permission word with no negation in the next two words ("may not", "পারবে না" do not count)."""
    t = norm(text)
    for m in find_words(t, DUTY_WORDS["PERMISSION"]):
        following = _tokens(t[m.end(): m.end() + 60])[:2]
        if not any(tok in NEGATION_TOKENS for tok in following):
            return True
    return False


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
_MONTHS: Dict[str, int] = {}


def _add_months(names: Sequence[str], number: int) -> None:
    for n in names:
        _MONTHS[norm(n)] = number


_add_months(("january", "jan"), 1)
_add_months(("february", "feb"), 2)
_add_months(("march", "mar"), 3)
_add_months(("april", "apr"), 4)
_add_months(("may",), 5)
_add_months(("june", "jun"), 6)
_add_months(("july", "jul"), 7)
_add_months(("august", "aug"), 8)
_add_months(("september", "sept", "sep"), 9)
_add_months(("october", "oct"), 10)
_add_months(("november", "nov"), 11)
_add_months(("december", "dec"), 12)
_add_months(("জানুয়ারি", "জানুয়ারী", "জানুয়ারি", "জানুআরি"), 1)
_add_months(("ফেব্রুয়ারি", "ফেব্রুয়ারী", "ফেব্রুআরি", "ফেব্রুয়ারী"), 2)
_add_months(("মার্চ",), 3)
_add_months(("এপ্রিল", "এপ্রিল"), 4)
_add_months(("মে",), 5)
_add_months(("জুন",), 6)
_add_months(("জুলাই",), 7)
_add_months(("আগস্ট", "আগষ্ট", "আগস্ট"), 8)
_add_months(("সেপ্টেম্বর", "সেপ্টেম্বর"), 9)
_add_months(("অক্টোবর", "অক্টোবর"), 10)
_add_months(("নভেম্বর", "নভেম্বর"), 11)
_add_months(("ডিসেম্বর", "ডিসেম্বর"), 12)

_MONTH_ALT = "|".join(re.escape(m) for m in sorted(_MONTHS, key=len, reverse=True))
# A month name must not be glued to other letters on either side.
_M = rf"(?<![a-z{_BANGLA}])({_MONTH_ALT})(?![a-z{_BANGLA}])"
_YEAR = r"(\d{4}|\d{2})(?!\d)"

_DATE_PATTERNS = [
    ("DMY_NUM", re.compile(r"(?<![\d/.\-])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*" + _YEAR)),
    ("ISO", re.compile(r"(?<![\d/.\-])(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")),
    ("D_MONTH_Y", re.compile(r"(?<![\d/.\-])(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?" + _M + r"\.?,?\s*'?" + _YEAR)),
    ("MONTH_D_Y", re.compile(_M + r"\.?\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*" + _YEAR)),
]


def _year(raw: str) -> int:
    y = int(raw)
    if len(raw) == 2:
        return 2000 + y if y <= 50 else 1900 + y
    return y


def _make_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def date_matches(text: str) -> List[Tuple[int, int, date]]:
    """(start, end, date) of each date written in the text, day first, no overlaps. Offsets are into norm(text)."""
    t = norm(text)
    taken: List[Tuple[int, int]] = []
    found: List[Tuple[int, int, date]] = []
    for name, pat in _DATE_PATTERNS:
        for m in pat.finditer(t):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            g = m.groups()
            d: Optional[date]
            if name == "DMY_NUM":
                d = _make_date(_year(g[2]), int(g[1]), int(g[0]))
            elif name == "ISO":
                d = _make_date(int(g[0]), int(g[1]), int(g[2]))
            elif name == "D_MONTH_Y":
                d = _make_date(_year(g[2]), _MONTHS[g[1]], int(g[0]))
            else:
                d = _make_date(_year(g[2]), _MONTHS[g[0]], int(g[1]))
            if d is None:
                continue
            taken.append((s, e))
            found.append((s, e, d))
    found.sort()
    return found


def dates_in(text: str) -> Set[date]:
    """Every date written in the text. Bangla-calendar dates (বৈশাখ ...) are not converted."""
    return {d for _s, _e, d in date_matches(text)}


def has_immediate_effect(text: str) -> bool:
    return has_any(text, IMMEDIATE_EFFECT, mode="stem")


def parse_iso_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", str(value))
    if not m:
        return None
    return _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def date_words(d: date) -> str:
    return f"{d.day} {d.strftime('%B')} {d.year}"


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
_PERCENT = r"\s?(?:%|শতাংশ|per\s?cent|percent)"
_NUMBER_WORD_ALT = "|".join(re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True))
_NUMBER_RE = re.compile(
    r"(?<![a-z0-9])(?:(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(" + _PERCENT + r")?"
    r"|(" + _NUMBER_WORD_ALT + r")(?![a-z0-9]))"
)


def _clean_number(raw: str) -> str:
    s = raw.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    # "06" and "০৬" are 6 (Bangladesh Bank writes small numbers with a leading zero).
    if "." in s:
        whole, frac = s.split(".", 1)
        s = (whole.lstrip("0") or "0") + "." + frac
    else:
        s = s.lstrip("0")
    return s or "0"


# Bangla number words, matched as whole words ("তিন মাস" is 3). নয় (9) is left out: it also means "not".
BANGLA_NUMBER_WORDS: Dict[str, str] = {
    "এক": "1", "দুই": "2", "তিন": "3", "চার": "4", "পাঁচ": "5", "ছয়": "6", "সাত": "7", "আট": "8", "দশ": "10",
    "বারো": "12", "পনের": "15", "পনেরো": "15", "বিশ": "20", "ত্রিশ": "30", "ষাট": "60", "নব্বই": "90",
}


def numbers_in(text: str) -> Counter:
    """The numbers written in the text, as a multiset of strings. Dates are removed first (they are checked as dates).

    "1,00,000" gives 100000, "২.৫%" gives 2.5%, "5.50" gives 5.5, "twelve" gives 12.
    A percent sign (or শতাংশ) stays with its number.
    """
    t = norm(text)
    chars = list(t)
    for s, e, _d in date_matches(t):
        for i in range(s, e):
            chars[i] = " "
    t = "".join(chars)
    out: Counter = Counter()
    for m in _NUMBER_RE.finditer(t):
        if m.group(3):
            out[NUMBER_WORDS[m.group(3)]] += 1
            continue
        n = _clean_number(m.group(1))
        if m.group(2):
            n += "%"
        out[n] += 1
    for word, value in BANGLA_NUMBER_WORDS.items():
        found = len(_word_pattern(word, "whole").findall(t))
        if found:
            out[value] += found
    return out


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
def entity_for(value: Optional[str]) -> Optional[str]:
    """The one entity of section 3.4 that a value names, or None when it names none or several."""
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    key = raw.upper().replace(" ", "_").replace("-", "_")
    if key in ENTITIES:
        return key
    if key in LEGACY_ENTITY_NAMES:
        return LEGACY_ENTITY_NAMES[key]
    best: Dict[str, int] = {}
    for name, aliases in ENTITIES.items():
        for alias in aliases:
            if find_words(raw, (alias,), mode="stem"):
                best[name] = max(best.get(name, 0), len(norm(alias)))
    if not best:
        return None
    top = max(best.values())
    winners = [n for n, length in best.items() if length == top]
    return winners[0] if len(winners) == 1 else None


def alias_in(entity: str, text: str) -> bool:
    return has_any(text, ENTITIES.get(entity, ()), mode="stem")


def entity_names_for_prompt() -> str:
    return ", ".join(ENTITIES)
