import sqlite3, json, sys
con = sqlite3.connect("file:data/regwatch.db?mode=ro", uri=True, timeout=30)
cur = con.cursor()
def q(sql, *a):
    return cur.execute(sql, a).fetchall()
print("tables:", [r[0] for r in q("select name from sqlite_master where type='table'")])
print("doc status:", q("select publication_status, count(*) from documents group by 1"))
print("page status:", q("select quality_status, extraction_method, count(*) from document_pages group by 1,2"))
print("analyses:", q("select publication_decision, count(*) from document_analyses group by 1"))
