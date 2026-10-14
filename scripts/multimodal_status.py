#!/usr/bin/env python3
"""Summarize existing smoke evidence without starting any model calls."""
import json
from pathlib import Path
from reflective_harness.registry import discover,get
ROOT=Path(__file__).resolve().parents[1]
RUNS={'longpuzzlebench':'multi-smoke-longpuzzle-002','gamedevbench':'multi-smoke-gamedev-001',
      'a2z':'multi-smoke-a2z-001','scivisagentbench':'multi-smoke-scivis-001','edithero':'multi-smoke-edithero-001'}
def main():
 rows=[]
 for name in discover():
  capability=get(name,ROOT).doctor();run=ROOT/'runs'/RUNS[name] if name in RUNS else None
  row={'benchmark':name,'capability':capability,'run':str(run) if run else None}
  if run and (run/'result.json').exists():row['result']=json.loads((run/'result.json').read_text())
  elif run and (run/'error.json').exists():row['error']=json.loads((run/'error.json').read_text())
  else:row['test_status']='not_run' if not run else 'in_progress_or_incomplete'
  rows.append(row)
 print(json.dumps({'schema_version':1,'rows':rows},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
