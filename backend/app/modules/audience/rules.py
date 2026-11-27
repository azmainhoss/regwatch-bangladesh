"""Who a circular is addressed to, read from its addressee line ("Managing Directors of all scheduled banks",
"Authorized Dealers in Bangladesh", "সকল তফসিলি ব্যাংক") with the department as a fallback. No AI.
Checked on 2026-11-28 against 664 analysed circulars: scheduled banks 99% correct / 95% found, authorised dealers
99% / 98%, NBFIs 92% / 89%. Islamic banks, MFS and payment providers are usually named inside the text, so the
checked analysis is the better source for those."""
import re
from typing import Optional, Set, Tuple

PATTERNS = [
    ("AUTHORIZED_DEALER", r"authori[sz]ed\s+dealer|\bAD\s+branch|\bADs\b|অনুমোদিত\s*ডিলার|এডি\s*শাখা"),
    ("NBFI", r"financial\s+institution|finance\s+compan|non-?bank|\bNBFI|আর্থিক\s*প্রতিষ্ঠান|ফাইন্যান্স\s*কোম্পানি|ফাইনান্স\s*কোম্পানি"),
    ("SCHEDULED_BANK", r"scheduled\s+bank|all\s+banks|তফসিলি\s*ব্যাংক|তফসিলী\s*ব্যাংক|সকল\s*ব্যাংক"),
    ("ISLAMIC_BANK", r"islami[ck]\s+shari|shari'?ah?\s+based|islamic\s+bank|ইসলামী\s*শরী|শরীয়াহ্?\s*ভিত্তিক"),
    ("MOBILE_FINANCIAL_SERVICE", r"mobile\s+financial|\bMFS\b|মোবাইল\s*ফাইন্যান্সিয়াল"),
    ("PAYMENT_SERVICE_PROVIDER", r"payment\s+(system\s+operator|service\s+provider)|\bPSOs?\b|\bPSPs?\b"),
    ("MONEY_CHANGER", r"money\s*changer|মানি\s*চেঞ্জার"),
    ("OFFSHORE_BANKING_UNIT", r"off-?shore\s+banking|অফশোর"),
    ("EXCHANGE_HOUSE", r"exchange\s+house"),
    ("MICROFINANCE_INSTITUTION", r"micro-?finance|ক্ষুদ্রঋণ"),
]
# Named in the first pages (not only the addressee line): reliable for these two only.
BODY_ENTITIES = {"OFFSHORE_BANKING_UNIT", "MONEY_CHANGER"}
DEPARTMENTS = [
    (r"^FE", {"AUTHORIZED_DEALER"}),
    (r"^DFIM", {"NBFI"}),
    (r"^IBRPD", {"ISLAMIC_BANK", "SCHEDULED_BANK"}),
    (r"^(BRPD|BRRD|DOS|DBI|ACD|SFD|GBCSRD|SMESPD|SDAD|DMD|BBRD)", {"SCHEDULED_BANK"}),
    (r"^PSD", {"PAYMENT_SERVICE_PROVIDER"}),
]
_SALUTATION = re.compile(r"প্রিয়\s*মহোদয়|Dear\s+Sir|Dear\s+Madam|Dear\s+all", re.I)


def _header(text: str) -> str:
    m = _SALUTATION.search(text or "")
    return (text or "")[: m.start() if m and m.start() < 1500 else 700]


def derive(reference: Optional[str], title: Optional[str], first_page: Optional[str], first_pages: Optional[str] = "") -> Tuple[Set[str], str]:
    """(audiences, source) where source is ADDRESSEE or DEPARTMENT; empty set when nothing is found."""
    head = _header(first_page or "") + "\n" + (title or "")
    out = {e for e, p in PATTERNS if re.search(p, head, re.I)}
    out |= {e for e, p in PATTERNS if e in BODY_ENTITIES and re.search(p, first_pages or "", re.I)}
    if re.match(r"^IBRPD", reference or "", re.I):
        out |= {"ISLAMIC_BANK", "SCHEDULED_BANK"}
    if out:
        return out, "ADDRESSEE"
    for pattern, entities in DEPARTMENTS:
        if re.search(pattern, reference or "", re.I):
            return set(entities), "DEPARTMENT"
    return set(), "ADDRESSEE"
