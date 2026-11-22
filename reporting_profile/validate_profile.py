import json, sys
from jsonschema import Draft202012Validator
schema = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "pba_reporting_profile_v0.1.schema.json"))
Draft202012Validator.check_schema(schema)
doc = json.load(open(sys.argv[1]))
errs = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.absolute_path))
for e in errs: print("INVALID", "/".join(map(str, e.absolute_path)) or "<root>", "-", e.message[:160])
print("VALID" if not errs else f"{len(errs)} violation(s)"); sys.exit(1 if errs else 0)
