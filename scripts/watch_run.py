"""Read-only live status; never polls a provider or invokes models."""
import json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
for task in sorted((a.run/'tasks').glob('task_*')):
    result=task/'final/result.json'
    if result.exists():
        d=json.loads(result.read_text());print(task.name,d['status'],'score',d['internal_score']);continue
    statuses=[]
    for event in task.rglob('events.jsonl'):
        if (event.parent/'execution.json').exists() or (event.parent.parent/'complete.json').exists():continue
        lines=event.read_text(errors='replace').splitlines()
        if lines:
            last=json.loads(lines[-1]);item=last.get('item',{})
            statuses.append(str(event.parent.parent.parent.relative_to(task))+': '+last.get('type','')+' '+str(item.get('type','')))
    print(task.name,'; '.join(statuses) or 'queued/checkpointed')
