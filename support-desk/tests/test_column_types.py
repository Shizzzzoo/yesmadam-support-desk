import glob, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.jsonc import load

# Valid Lemma DatastoreDataType values (from `lemma table schema` scaffold).
VALID = {"BOOLEAN", "DATE", "DATETIME", "ENUM", "FILE_PATH", "FLOAT",
         "INTEGER", "JSON", "SERIAL", "TEXT", "USER", "UUID", "VECTOR"}

bad = []
for path in glob.glob("tables/*/*.json"):
    t = load(path)
    for c in t["columns"]:
        if c["type"] not in VALID:
            bad.append(f"{t['name']}.{c['name']} -> invalid type {c['type']}")
assert not bad, "Invalid column types:\n  " + "\n  ".join(bad)
print("test_column_types OK")
