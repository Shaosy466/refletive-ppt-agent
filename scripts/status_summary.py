"""Compact status from durable result/checkpoint files, no model calls."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
m=json.loads((a.run/'manifest.json').read_text())
for tid in m['tasks']:
 t=a.run/'tasks'/tid;r=t/'final/result.json'
 if r.exists():
  d=json.loads(r.read_text());print(f"{tid}: {d['status']} score={d['internal_score']} calls={d['agent_calls']}")
 else:
  rounds=list(t.glob('candidates/*/judge/round-*/ranked.json'));author=list(t.glob('candidates/*/author.complete.json'))
  print(f'{tid}: pending/running; authors={len(author)}, judge_rounds={len(rounds)}')
