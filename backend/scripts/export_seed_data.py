import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/regwatch.db")
OUTPUT_PATH = Path("backend/app/fixtures/production_seed.json")

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cur = conn.cursor()

    data = {}

    # 1. Institutions & Departments
    data["institutions"] = cur.execute("SELECT * FROM institutions").fetchall()
    data["institution_departments"] = cur.execute("SELECT * FROM institution_departments").fetchall()

    # 2. Users & Profiles & Organizations
    data["users"] = cur.execute("SELECT * FROM users WHERE email IN ('admin@regwatch.bd', 'cco@abcbank.bd', 'cco@nationalbank.bd')").fetchall()
    data["user_profiles"] = cur.execute("SELECT * FROM user_profiles").fetchall()
    data["organizations"] = cur.execute("SELECT * FROM organizations").fetchall()
    data["departments"] = cur.execute("SELECT * FROM departments").fetchall()
    data["organization_members"] = cur.execute("SELECT * FROM organization_members").fetchall()

    # 3. Sources
    data["sources"] = cur.execute("SELECT * FROM sources").fetchall()

    # 4. Genuine Documents & Versions
    # Exclude synthetic benchmark duplicates with title like 'Sample Test Circular'
    docs = cur.execute("""
        SELECT * FROM documents 
        WHERE (title NOT LIKE 'Sample%' AND reference_number NOT LIKE 'UTD%' AND reference_number NOT LIKE 'VCP%')
           OR reference_number IN ('BRPD Circular No. 15/2024', 'BRPD Circular No. 16/2024', 'SMESPD Circular No. 05/2026')
    """).fetchall()
    doc_ids = [d["id"] for d in docs]
    data["documents"] = docs
    print(f"Exporting {len(docs)} genuine documents...")

    placeholders = ",".join(f"'{did}'" for did in doc_ids)
    
    versions = cur.execute(f"SELECT * FROM document_versions WHERE document_id IN ({placeholders})").fetchall()
    version_ids = [v["id"] for v in versions]
    data["document_versions"] = versions
    print(f"Exporting {len(versions)} document versions...")

    v_placeholders = ",".join(f"'{vid}'" for vid in version_ids) if version_ids else "''"

    pages = cur.execute(f"SELECT * FROM document_pages WHERE document_version_id IN ({v_placeholders})").fetchall()
    data["document_pages"] = pages
    print(f"Exporting {len(pages)} document pages...")

    analyses = cur.execute(f"SELECT * FROM document_analyses WHERE document_version_id IN ({v_placeholders})").fetchall()
    analysis_ids = [a["id"] for a in analyses]
    data["document_analyses"] = analyses
    print(f"Exporting {len(analyses)} document analyses...")

    provisions = cur.execute(f"SELECT * FROM provisions WHERE document_version_id IN ({v_placeholders})").fetchall()
    data["provisions"] = provisions
    print(f"Exporting {len(provisions)} provisions...")

    obligations = cur.execute(f"SELECT * FROM obligations WHERE document_version_id IN ({v_placeholders})").fetchall()
    data["obligations"] = obligations
    print(f"Exporting {len(obligations)} obligations...")

    a_placeholders = ",".join(f"'{aid}'" for aid in analysis_ids) if analysis_ids else "''"
    claims = cur.execute(f"SELECT * FROM analysis_claims WHERE analysis_id IN ({a_placeholders})").fetchall()
    claim_ids = [c["id"] for c in claims]
    data["analysis_claims"] = claims
    print(f"Exporting {len(claims)} analysis claims...")

    c_placeholders = ",".join(f"'{cid}'" for cid in claim_ids) if claim_ids else "''"
    citations = cur.execute(f"SELECT * FROM claim_citations WHERE claim_id IN ({c_placeholders})").fetchall()
    data["claim_citations"] = citations
    print(f"Exporting {len(citations)} claim citations...")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f" Successfully written {OUTPUT_PATH.stat().st_size} bytes to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
