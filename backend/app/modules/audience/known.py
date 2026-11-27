"""Guess a reader's institution type from the company name they gave at sign-up, so most people never have to
answer the question. Only confident matches: anything else returns None and the reader is asked once."""
import re
from typing import Optional, Tuple

# (type, has AD branches). Names are matched as whole words after cleaning ("PLC", "Limited", dots removed).
_BANKS = {
    "STATE_OWNED_BANK": [
        "sonali bank", "janata bank", "agrani bank", "rupali bank", "basic bank", "bangladesh development bank", "bdbl",
    ],
    "SPECIALIZED_SCHEDULED": ["bangladesh krishi bank", "krishi bank", "rajshahi krishi unnayan bank", "rakub", "bkb"],
    "SPECIALIZED_BANK": [
        "ansar vdp unnayan bank", "ansar vdp", "karmasangsthan bank", "probashi kallyan bank", "palli sanchay bank",
        "jubilee bank", "grameen bank",
    ],
    "ISLAMIC_BANK": [
        "islami bank bangladesh", "ibbl", "al arafah islami bank", "al-arafah islami bank", "social islami bank",
        "exim bank", "export import bank of bangladesh", "first security islami bank", "fsibl", "shahjalal islami bank",
        "union bank", "global islami bank", "standard islami bank", "standard bank", "icb islamic bank",
        "sammilito islami bank", "united islami bank",
    ],
    "FOREIGN_BANK": [
        "standard chartered", "hsbc", "citibank", "commercial bank of ceylon", "state bank of india", "habib bank",
        "national bank of pakistan", "woori bank", "bank alfalah",
    ],
    "CONVENTIONAL_BANK": [
        "ab bank", "bangladesh commerce bank", "bank asia", "brac bank", "city bank", "dhaka bank", "dutch bangla bank",
        "dutch-bangla bank", "dbbl", "eastern bank", "ebl", "ific bank", "jamuna bank", "meghna bank", "mercantile bank",
        "midland bank", "modhumoti bank", "mutual trust bank", "mtb", "national bank", "ncc bank", "nrb bank",
        "nrbc bank", "nrb commercial bank", "one bank", "padma bank", "premier bank", "prime bank", "pubali bank",
        "south bangla agriculture and commerce bank", "sbac bank", "shimanto bank", "southeast bank", "trust bank",
        "united commercial bank", "ucb", "uttara bank", "community bank", "bengal commercial bank", "citizens bank",
        "citizens plc",
    ],
}
_OTHERS = {
    "NBFI": [
        "idlc", "ipdc", "lankabangla", "lanka bangla", "dbh finance", "delta brac housing", "union capital",
        "united finance", "bangladesh finance", "phoenix finance", "iidfc", "national housing finance",
        "islamic finance and investment", "uttara finance", "prime finance", "peoples leasing", "fas finance",
        "international leasing", "bifc", "fareast finance", "gsp finance", "hajj finance", "meridian finance",
        "strategic finance", "alliance finance", "bay leasing", "cvc finance", "idcol", "midas financing",
        "infrastructure development company", "first finance", "premier leasing", "reliance finance",
        "agrani sme financing", "industrial and infrastructure development finance",
    ],
    "MFS_PSP": ["bkash", "nagad", "upay", "mcash", "surecash", "rocket", "ok wallet", "ssl wireless", "sslcommerz", "portwallet", "shurjopay"],
    "AUDITOR": [
        "chartered accountants", "chartered accountant", "acnabin", "rahman rahman huq", "rrh", "hoda vasi",
        "a qasem", "mabs", "pinaki", "kpmg", "pwc", "pricewaterhousecoopers", "deloitte", "ernst", "grant thornton",
        "k m hasan", "shafiq basak", "howladar yunus", "mahfel huq", "atik khaled", "toha khan", "hussain farhad",
        "syful shamsul", "aziz halim", "malek siddiqui", "snehasish mahmud", "fames r", "ahmed zaker",
    ],
}


def _clean(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[.,()]", " ", s)
    s = re.sub(r"\b(plc|ltd|limited|pvt|private)\b", " ", s)
    return " " + re.sub(r"\s+", " ", s).strip() + " "


def _has(clean: str, key: str) -> bool:
    return f" {key} " in clean


def guess_institution(company: Optional[str]) -> Optional[Tuple[str, bool]]:
    """(institution type, has AD branches) for a recognised company name, else None."""
    clean = _clean(company or "")
    if len(clean.strip()) < 2:
        return None
    # Audit firms first ("& Co., Chartered Accountants" can contain a bank-like word).
    for key in _OTHERS["AUDITOR"]:
        if _has(clean, key):
            return "AUDITOR", False
    for kind, keys in _BANKS.items():
        for key in keys:
            if _has(clean, key):
                if kind == "SPECIALIZED_SCHEDULED":
                    return "STATE_OWNED_BANK", True
                return kind, kind != "SPECIALIZED_BANK"
    for kind in ("NBFI", "MFS_PSP"):
        for key in _OTHERS[kind]:
            if _has(clean, key):
                return kind, False
    return None
