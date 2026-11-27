"""Institution types a reader picks, and which circular audiences each one receives."""
from typing import Dict, FrozenSet, Optional

ALL = "ALL"

# Labels used in reasons and on the circular page ("Applies to authorised dealers").
ENTITY_LABELS: Dict[str, str] = {
    "SCHEDULED_BANK": "all scheduled banks",
    "AUTHORIZED_DEALER": "authorised dealers (AD branches)",
    "NBFI": "finance companies (NBFIs)",
    "ISLAMIC_BANK": "Islamic banks",
    "STATE_OWNED_BANK": "state-owned banks",
    "SPECIALIZED_BANK": "specialised banks",
    "FOREIGN_BANK": "foreign banks",
    "PRIVATE_COMMERCIAL_BANK": "private commercial banks",
    "MOBILE_FINANCIAL_SERVICE": "mobile financial services",
    "PAYMENT_SERVICE_PROVIDER": "payment service providers",
    "MONEY_CHANGER": "money changers",
    "OFFSHORE_BANKING_UNIT": "offshore banking units",
    "EXCHANGE_HOUSE": "exchange houses",
    "MICROFINANCE_INSTITUTION": "microfinance institutions",
}
KNOWN_ENTITIES = frozenset(ENTITY_LABELS)

# code -> (label, "your institution is ..." phrase, audiences, is a bank that can hold an AD licence)
INSTITUTION_TYPES: Dict[str, tuple] = {
    "CONVENTIONAL_BANK": ("Conventional bank", "a conventional bank", {"SCHEDULED_BANK", "PRIVATE_COMMERCIAL_BANK"}, True),
    "ISLAMIC_BANK": ("Islamic bank", "an Islamic bank", {"SCHEDULED_BANK", "ISLAMIC_BANK", "PRIVATE_COMMERCIAL_BANK"}, True),
    "STATE_OWNED_BANK": ("State-owned bank", "a state-owned bank", {"SCHEDULED_BANK", "STATE_OWNED_BANK"}, True),
    "SPECIALIZED_BANK": ("Specialised bank (not scheduled)", "a specialised bank", {"SPECIALIZED_BANK"}, False),
    "FOREIGN_BANK": ("Foreign bank", "a foreign bank", {"SCHEDULED_BANK", "FOREIGN_BANK"}, True),
    "NBFI": ("NBFI / finance company", "a finance company", {"NBFI"}, False),
    "MFS_PSP": ("MFS / payment provider", "a payment or mobile financial service provider", {"MOBILE_FINANCIAL_SERVICE", "PAYMENT_SERVICE_PROVIDER"}, False),
    "MONEY_CHANGER": ("Money changer", "a money changer", {"MONEY_CHANGER"}, False),
    "AUDITOR": ("Auditor / consultant", "an auditor or consultant", {ALL}, False),
    "COMPANY": ("Company (importer / exporter)", "an importer or exporter", {"AUTHORIZED_DEALER"}, False),
    "OTHER": ("Other", "", set(), False),
}

# Workspace (organisation) entity types, for members who have not picked a type themselves.
ORG_TYPE_MAP = {
    "COMMERCIAL_BANK": ("CONVENTIONAL_BANK", True),
    "ISLAMIC_BANK": ("ISLAMIC_BANK", True),
    "NBFI": ("NBFI", False),
    "LAW_FIRM": ("AUDITOR", False),
    "CONSULTING_FIRM": ("AUDITOR", False),
}


def audiences_for(kind: Optional[str], has_ad: Optional[bool]) -> FrozenSet[str]:
    if not kind or kind not in INSTITUTION_TYPES:
        return frozenset()
    out = set(INSTITUTION_TYPES[kind][2])
    if has_ad and INSTITUTION_TYPES[kind][3]:
        out |= {"AUTHORIZED_DEALER", "OFFSHORE_BANKING_UNIT"}
    return frozenset(out)
