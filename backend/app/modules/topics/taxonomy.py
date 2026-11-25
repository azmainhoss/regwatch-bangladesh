"""The fixed list of subject categories a circular can belong to.

A circular can sit in several categories at once (they are not mutually exclusive). The list is
fixed in code so filters, search and the classifier always agree on the names.

`words` are the short forms and plain phrases bank staff type when they look for the subject. Search
uses them too: typing "ECL" also finds circulars that only say "expected credit loss".
"""
from typing import Dict, List, NamedTuple, Tuple


class Topic(NamedTuple):
    code: str
    label: str
    hint: str  # what belongs here, for the classifier
    words: Tuple[str, ...] = ()


TOPICS: List[Topic] = [
    Topic("ECL", "Expected credit loss (ECL)", "IFRS 9 expected credit loss, staging of loans, ECL models and provisioning under IFRS 9",
          ("ECL", "expected credit loss", "IFRS 9", "IFRS-9")),
    Topic("PROVISION", "Loan classification and provisioning", "loan classification (SMA, SS, DF, BL), provisioning rates, specific and general provision",
          ("provision", "provisioning", "loan classification", "classified loan", "SMA", "bad loan", "শ্রেণীকরণ", "প্রভিশন", "সঞ্চিতি")),
    Topic("DEFAULT_LOANS", "Rescheduling, write-off and default loans", "rescheduling, restructuring, write-off, exit, recovery of defaulted or stressed loans",
          ("reschedule", "rescheduling", "restructuring", "write-off", "write off", "defaulter", "default loan", "NPL", "non-performing", "পুনঃতফসিল", "অবলোপন", "খেলাপি")),
    Topic("CAPITAL", "Capital adequacy (Basel)", "capital adequacy ratio, Basel III, CRAR, capital buffers, leverage ratio, ICAAP, SRP",
          ("capital adequacy", "CRAR", "Basel", "CAR", "leverage ratio", "ICAAP", "capital conservation buffer", "মূলধন")),
    Topic("LIQUIDITY", "Liquidity, CRR and SLR", "cash reserve ratio, statutory liquidity ratio, LCR, NSFR, ADR/IDR, liquidity support",
          ("CRR", "SLR", "LCR", "NSFR", "ADR", "IDR", "liquidity", "cash reserve", "advance deposit ratio", "তারল্য")),
    Topic("INTEREST_RATE", "Interest rates and pricing", "lending and deposit interest rates, SMART rate, rate caps, spread, pricing of loans",
          ("interest rate", "SMART", "lending rate", "deposit rate", "spread", "rate of interest", "সুদহার")),
    Topic("CREDIT", "Lending and credit risk", "general credit policy, large loans, single borrower limit, credit risk management, loan approval, collateral",
          ("credit risk", "large loan", "single borrower", "exposure limit", "collateral", "credit policy", "loan", "ঋণ")),
    Topic("SME_AGRI", "SME, agriculture and refinance schemes", "CMSME, SME finance, agricultural and rural credit, refinance and stimulus schemes, women entrepreneurs",
          ("SME", "CMSME", "MSME", "agricultural credit", "agri", "refinance", "stimulus", "কৃষি", "এসএমই", "পুনঃঅর্থায়ন")),
    Topic("GREEN", "Green and sustainable finance", "green banking, sustainable finance, climate risk, ESG, environmental risk management",
          ("green", "sustainable finance", "climate", "ESG", "environmental risk", "সবুজ", "টেকসই")),
    Topic("FOREX", "Foreign exchange and remittance", "foreign exchange transactions, exchange rate, FX accounts, inward remittance, outward remittance, nostro, exchange houses",
          ("foreign exchange", "FX", "forex", "remittance", "exchange rate", "nostro", "foreign currency", "বৈদেশিক মুদ্রা", "রেমিট্যান্স")),
    Topic("TRADE", "Import, export and trade", "import and export payments, LC, export retention quota, EDF, trade finance, deferred payment",
          ("import", "export", "LC", "letter of credit", "ERQ", "EDF", "trade finance", "আমদানি", "রপ্তানি")),
    Topic("AML", "AML, CFT and KYC", "anti money laundering, combating terrorist financing, KYC/CDD, STR/CTR, sanctions screening (often BFIU)",
          ("AML", "CFT", "KYC", "CDD", "money laundering", "terrorist financing", "STR", "CTR", "BFIU", "sanctions", "মানিলন্ডারিং")),
    Topic("PAYMENTS", "Payment systems, MFS and digital banking", "payment systems, MFS, mobile and internet banking, RTGS, BEFTN, NPSB, digital banks, e-wallets, PSO/PSP",
          ("payment system", "MFS", "mobile financial", "RTGS", "BEFTN", "NPSB", "BACH", "digital bank", "internet banking", "e-wallet", "PSO", "PSP", "QR")),
    Topic("CARDS", "Credit and debit cards", "credit cards, debit cards, prepaid cards, card limits and card charges",
          ("credit card", "debit card", "prepaid card", "card", "কার্ড")),
    Topic("ICT", "ICT and cyber security", "ICT security, cyber security, IT risk, data protection, outsourcing of IT, cloud",
          ("ICT", "cyber", "IT security", "information security", "data protection", "cloud")),
    Topic("GOVERNANCE", "Corporate governance and board", "board of directors, MD/CEO, appointment of senior officials, bank company act governance rules, shareholders",
          ("governance", "board of directors", "director", "MD", "CEO", "managing director", "chairman", "পরিচালক")),
    Topic("INTERNAL_AUDIT", "Internal audit and internal control", "internal control and compliance, internal audit, ICC, audit committee, risk-based internal audit",
          ("internal audit", "internal control", "ICC", "audit committee", "compliance", "অভ্যন্তরীণ নিরীক্ষা")),
    Topic("FINANCIAL_STATEMENTS", "Financial statements and external audit", "preparation of financial statements, annual accounts, external auditors, disclosures, dividend declaration",
          ("financial statement", "annual report", "external audit", "auditor", "balance sheet", "dividend", "disclosure", "IFRS", "আর্থিক বিবরণী")),
    Topic("REPORTING", "Regulatory reporting and returns", "returns and statements banks must submit to Bangladesh Bank, reporting formats, reporting deadlines",
          ("return", "reporting", "statement submission", "report submission", "format", "রিটার্ন", "প্রতিবেদন")),
    Topic("RISK", "Risk management and stress testing", "core risk management, stress testing, risk appetite, market risk, operational risk",
          ("risk management", "stress test", "stress testing", "risk appetite", "market risk", "operational risk", "ঝুঁকি")),
    Topic("BRANCHES", "Branches, agent and sub-branch banking", "opening or closing branches, sub-branches, agent banking, booths, ATMs",
          ("branch", "sub-branch", "agent banking", "agent", "outlet", "booth", "ATM", "শাখা", "এজেন্ট")),
    Topic("CUSTOMER", "Customer protection and complaints", "customer service, complaint handling, financial inclusion, fair treatment, school banking, accounts for the poor",
          ("customer", "complaint", "financial inclusion", "consumer protection", "grievance", "গ্রাহক")),
    Topic("DEPOSITS", "Deposits and accounts", "deposit products, savings schemes, account opening rules, dormant accounts, deposit insurance",
          ("deposit", "savings", "account opening", "dormant", "unclaimed", "deposit insurance", "আমানত", "হিসাব")),
    Topic("CHARGES", "Bank charges and fees", "service charges, fees, schedule of charges, excise duty, waivers",
          ("charge", "fee", "service charge", "schedule of charges", "চার্জ", "ফি")),
    Topic("ISLAMIC", "Islamic banking", "Shariah-based banking, Islamic windows, mudaraba, sukuk, Islamic bank rules",
          ("Islamic", "Shariah", "Shari'ah", "mudaraba", "sukuk", "ইসলামী", "শরীয়াহ")),
    Topic("TREASURY", "Treasury, money market and securities", "money market, call money, repo, government bills and bonds, capital market investment by banks",
          ("treasury", "money market", "call money", "repo", "treasury bill", "bond", "capital market", "investment", "শেয়ার")),
    Topic("CURRENCY", "Currency notes and coins", "currency management, banknotes, soiled notes, coins, cash handling, currency chest",
          ("currency note", "banknote", "note", "coin", "soiled", "cash", "নোট", "মুদ্রা")),
    Topic("NBFI", "NBFIs and finance companies", "rules for non-bank financial institutions and finance companies (DFIM)",
          ("NBFI", "finance company", "financial institution", "DFIM", "leasing", "আর্থিক প্রতিষ্ঠান")),
    Topic("HR", "Staff, HR and training", "staff salary, recruitment, training, code of conduct, staff loans",
          ("staff", "employee", "recruitment", "training", "salary", "HR", "কর্মকর্তা", "কর্মচারী")),
    Topic("OPERATIONS", "Bank hours, holidays and operations", "banking hours, holidays, office timing, general operations and housekeeping",
          ("holiday", "banking hours", "office time", "closure", "ছুটি", "লেনদেন সময়")),
    Topic("OTHER", "Other", "anything that fits none of the categories above", ()),
]

TOPIC_BY_CODE: Dict[str, Topic] = {t.code: t for t in TOPICS}
CODES = [t.code for t in TOPICS]


# Short forms and their spelled-out names. Search treats every name in a group as the same word.
SYNONYMS: List[Tuple[str, ...]] = [
    ("ECL", "expected credit loss", "IFRS 9", "IFRS-9"),
    ("CRR", "cash reserve ratio", "cash reserve requirement"),
    ("SLR", "statutory liquidity ratio", "statutory liquidity requirement"),
    ("LCR", "liquidity coverage ratio"),
    ("NSFR", "net stable funding ratio"),
    ("ADR", "advance deposit ratio", "advance-deposit ratio"),
    ("IDR", "investment deposit ratio"),
    ("CRAR", "capital to risk weighted asset ratio", "capital adequacy ratio"),
    ("CAR", "capital adequacy ratio"),
    ("ICAAP", "internal capital adequacy assessment process"),
    ("KYC", "know your customer"),
    ("CDD", "customer due diligence"),
    ("AML", "anti money laundering", "anti-money laundering", "money laundering"),
    ("CFT", "combating the financing of terrorism", "terrorist financing"),
    ("STR", "suspicious transaction report"),
    ("SAR", "suspicious activity report"),
    ("CTR", "cash transaction report"),
    ("MFS", "mobile financial service", "mobile financial services"),
    ("NPL", "non-performing loan", "nonperforming loan", "classified loan"),
    ("SMA", "special mention account"),
    # Loan classification grades (BRPD master circulars on classification and provisioning).
    ("STD", "standard", "unclassified"),
    ("SS", "sub-standard", "substandard"),
    ("DF", "doubtful"),
    ("BL", "bad/loss", "bad loss", "bad & loss"),
    ("UC", "unclassified"),
    ("SME", "small and medium enterprise", "CMSME", "MSME"),
    ("CMSME", "cottage, micro, small and medium", "SME"),
    ("LC", "letter of credit", "letters of credit"),
    ("ERQ", "export retention quota"),
    ("EDF", "export development fund"),
    ("ICC", "internal control and compliance"),
    ("RTGS", "real time gross settlement"),
    ("BEFTN", "electronic fund transfer network"),
    ("NPSB", "national payment switch"),
    ("PSO", "payment system operator"),
    ("PSP", "payment service provider"),
    ("FX", "foreign exchange", "forex"),
    ("MD", "managing director"),
    ("CEO", "chief executive officer", "managing director"),
    ("CAMLCO", "chief anti money laundering compliance officer"),
    ("BAMLCO", "branch anti money laundering compliance officer"),
    ("NBFI", "non-bank financial institution", "finance company"),
    ("provision", "provisioning", "প্রভিশন", "সঞ্চিতি"),
    ("reschedule", "rescheduling", "পুনঃতফসিল"),
    ("write-off", "write off", "written off", "অবলোপন"),
]


def words_for(term: str) -> List[str]:
    """Other ways to write a search word. "ECL" gives ["expected credit loss", "IFRS 9", "IFRS-9"].

    Only an exact (case-insensitive) match of a listed name counts, so ordinary words are not expanded.
    """
    low = term.strip().lower()
    out: List[str] = []
    for group in SYNONYMS:
        if any(w.lower() == low for w in group):
            for w in group:
                if w.lower() != low and w not in out:
                    out.append(w)
    return out


def topics_for(term: str) -> List[str]:
    """Category codes a search word names: "ECL" -> ["ECL"], "provision" -> ["PROVISION"]."""
    low = term.strip().lower()
    if len(low) < 2:
        return []
    found = []
    for t in TOPICS:
        if t.code.lower() == low or any(w.lower() == low for w in t.words):
            found.append(t.code)
    return found


# Short forms such as ECL or CRR. Search matches these as whole words only (with an optional plural "s"),
# so "ECL" never matches inside "declaration". Ordinary short words ("loan") still match inside longer ones.
ACRONYMS = {
    w.upper()
    for group in [*SYNONYMS, *(t.words for t in TOPICS)]
    for w in group
    if 2 <= len(w) <= 6 and w.replace("-", "").isalnum() and w.upper() == w and not any("ঀ" <= ch <= "৿" for ch in w)
}
