from pathlib import Path
import csv, sys
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'paper/EVIDENCE_LEDGER.csv'
rows=list(csv.DictReader(p.open(encoding='utf-8')))
bad=[r for r in rows if r['status']=='verified' and (not r['artifact_path'] or not r['sha256'])]
if bad:
    print('Invalid verified evidence rows:', [r['claim_id'] for r in bad]); sys.exit(1)
print(f'Evidence ledger OK: {len(rows)} rows, {sum(r["status"]=="verified" for r in rows)} verified')
