"""Fork a frozen run into a new environment, reusing only verified generation.

No artifact validation, render, judge, consensus or feedback is reused. Original run is untouched.
All paid work remains accounted for in the copied budget ledger.
"""
import shutil,json,uuid
from pathlib import Path
from datetime import datetime,timezone
from .config import environment,ROOT
from .workspace import read_json,atomic_json,ConfigError,sha
from .checkpoints import restore,lock

def fork_generation(old:Path,config, repair_failures=False):
    old_manifest=read_json(old/'manifest.json')
    old_agent=read_json(old/'resolved-config.json')['agent']
    if any(old_agent[k]!=config['agent'][k] for k in ('model','reasoning_effort')):
        raise ConfigError('Replay requires the original model and effort; use run for a new model')
    if repair_failures:
        previous=read_json(old/'environment.json');current=environment(config)
        for key in ['fontconfig_sha256','libreoffice','fonts','packages','prompts_hash','upstream_commit','judge_protocol','agent']:
            if previous.get(key)!=current.get(key):raise ConfigError(f'Compatible recovery requires unchanged {key}')
    if old_manifest.get('inspect_pptx'):raise ConfigError('Generation replay requires a generation run')
    env=environment(config)
    run=Path(config['output']['root'])/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-replay-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
    atomic_json(run/'resolved-config.json',config);atomic_json(run/'environment.json',env)
    atomic_json(run/'manifest.json',{'tasks':old_manifest['tasks'],'inspect_pptx':None,'generation_reused_from':str(old),'recovery_migration':repair_failures})
    imported=[]
    for task_id in old_manifest['tasks']:
        src=old/'tasks'/task_id;dst=run/'tasks'/task_id
        if not src.exists():continue
        with lock(src/'task.lock'):
            if repair_failures:
                shutil.copytree(src,dst)
                final=dst/'final/result.json'
                if final.exists() and read_json(final)['status'] in ('INFRA_ERROR','CANCELLED'):
                    shutil.move(str(dst/'final'),str(dst/'previous-final'))
                # The bounded format repair may now reuse an otherwise valid raw model response.
                for response in dst.rglob('response.json'):
                    meta=response.parent.parent
                    if meta.name!='.harness' or (meta/'complete.json').exists():continue
                    execution=response.parent/'execution.json'
                    if execution.exists() and read_json(execution).get('exit_code')==0:
                        atomic_json(meta/'repair-existing.json',{'response_path':str(response.relative_to(dst))})
            else:dst.mkdir(parents=True)
            # Budget retains previously consumed calls and active processing time.
            if (src/'budget.json').exists():
                ledger=read_json(src/'budget.json');ledger['usage_complete']=False
                atomic_json(dst/'budget.json',ledger)
            for name in ['input','input-hashes.json','diagram-spec.json']:
                p=src/name
                if p.is_dir() and not repair_failures:shutil.copytree(p,dst/name)
                elif p.is_file():shutil.copy2(p,dst/name)
            if not repair_failures and (src/'understanding/.harness/complete.json').exists():
                restore(src/'understanding/.harness/complete.json')
                shutil.copytree(src/'understanding',dst/'understanding')
            author=src/'candidates/000/author.complete.json'
            if author.exists() and not repair_failures:
                restore(author)
                candidate=dst/'candidates/000';candidate.mkdir(parents=True)
                shutil.copytree(src/'candidates/000/source',candidate/'source')
                shutil.copy2(author,candidate/'author.complete.json')
                raw=src/'candidates/000/raw'
                if (raw/'build.complete.json').exists():
                    restore(raw/'build.complete.json');shutil.copytree(raw,candidate/'raw')
                imported.append(task_id)
            # Rebase only checkpoint file references; preserve original request/response evidence.
            for p in dst.rglob('*.json'):
                if not (p.name=='complete.json' or p.name.endswith('.complete.json')):continue
                d=read_json(p)
                if 'files' in d:
                    files={}
                    for filename,h in d['files'].items():
                        original=Path(filename)
                        if not original.is_relative_to(old):raise ConfigError('Checkpoint references outside original run')
                        new=run/original.relative_to(old)
                        if not new.is_file() or sha(new)!=h:raise ConfigError(f'Replay hash mismatch: {new}')
                        files[str(new)]=h
                    d['files']=files;atomic_json(p,d)
    atomic_json(run/'generation-reuse.json',{'original_run':str(old),'author_reused_tasks':imported,
                 'reused_validation':repair_failures,'reused_judgments':repair_failures,'previous_budget_included':True})
    import zipfile
    with zipfile.ZipFile(run/'implementation-snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ['src/pptbench_harness','prompts','schemas','configs']:
            for p in (ROOT/folder).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT))
    return run
