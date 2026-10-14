from __future__ import annotations
import json,re,shutil,sys,subprocess
from pathlib import Path
from PIL import Image
from .workspace import inside,sha,atomic_json,InputError

def task_ids(path):
    return [x.split('#')[0].strip() for x in Path(path).read_text().splitlines() if x.split('#')[0].strip()]

def materialize(config, ids, accept=False, resume=False):
    up=Path(config['dataset']['upstream_root'])
    argv=[sys.executable,'-m','arxiv_flow_dataset.task_materializer','--tasks-root',str(up/'benchmark/tasks'),
          '--manifest',str(up/'benchmark/materialization_manifest.jsonl'),'--license-audit',str(up/'benchmark/source_license_audit.jsonl'),
          '--output-root',config['dataset']['root'],'--cache-dir',str(up/'.cache/arxiv-sources')]
    for i in ids: argv+=['--task-id',i]
    if accept: argv+=['--accept-arxiv-terms']
    if resume: argv+=['--resume']
    return subprocess.call(argv,cwd=up)

def prepare_input(config,task_id,destination):
    if not re.fullmatch(r'task_\d{4}',task_id): raise InputError('Invalid task ID')
    from arxiv_flow_dataset.task_materializer import verify_materialized_task,pixel_sha256
    root=Path(config['dataset']['root'])/task_id
    up=Path(config['dataset']['upstream_root'])
    specs=[json.loads(x) for x in (up/'benchmark/materialization_manifest.jsonl').read_text().splitlines()]
    spec=next((x for x in specs if x['task_id']==task_id),None)
    if not spec: raise InputError('Task not in frozen benchmark')
    try: verify_materialized_task(root,spec)
    except (ValueError,OSError) as exc: raise InputError(f'Materialize/verify {task_id} first: {exc}') from exc
    destination.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'reference.png',destination/'reference.png')
    assets=[]
    for n,r in enumerate(spec['resources']):
        p=inside(root/'resources',r['file']); target=inside(destination/'assets',r['file'])
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target)
        with Image.open(p) as im:
            assets.append({'asset_id':f'asset_{n:03d}','path':'input/assets/'+r['file'],
                           'sha256':sha(p),'pixel_sha256':pixel_sha256(im),'width':im.width,'height':im.height})
    with Image.open(destination/'reference.png') as im: width,height=im.size
    task={'schema_version':1,'task_id':task_id,'reference_path':'input/reference.png','reference_sha256':sha(destination/'reference.png'),
          'reference_width':width,'reference_height':height,'approved_assets':assets,
          'constraints':{'slide_count':1,'native_editable':True,'approved_assets_required':True}}
    atomic_json(destination/'task.json',task)
    return task
