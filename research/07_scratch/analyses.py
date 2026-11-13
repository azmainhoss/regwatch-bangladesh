import sqlite3, json
con = sqlite3.connect("file:data/regwatch.db?mode=ro", uri=True, timeout=30)
cur = con.cursor()
rows = cur.execute("""select a.id, d.title, d.publication_status, a.model_name, a.prompt_version, a.citation_coverage_score,
 a.publication_decision, a.structured_payload, a.validation_errors, a.created_at, d.reference_number
 from document_analyses a join document_versions v on v.id=a.document_version_id join documents d on d.id=v.document_id order by a.created_at""").fetchall()
for r in rows:
    p = json.loads(r[7]) if r[7] else {}
    ve = json.loads(r[8]) if r[8] else []
    rels = [x.get("relationship_type") for x in p.get("relationships",[])]
    ia = p.get("impact_assessment") or {}
    print("---", (r[1] or "")[:70], "| doc:", r[2], "| model:", r[3], r[4], "| cov:", r[5], "| dec:", r[6], "| lang:", r[10], "|", r[9])
    print("   provs", len(p.get("provisions",[])), "obls", len(p.get("obligations",[])), "rels", rels, "sev", ia.get("overall_impact_severity"))
    print("   errors:", [(e.get("item_type"), e.get("status"), (e.get("issues") or [""])[0][:80]) for e in ve][:6])
    obl = p.get("obligations",[])
    print("   deadlines:", [o.get("explicit_deadline") for o in obl], "ents:", list({o.get("responsible_entity") for o in obl})[:4])
