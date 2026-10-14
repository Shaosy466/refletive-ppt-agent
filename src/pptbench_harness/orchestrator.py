from __future__ import annotations
import asyncio,shutil,uuid,sys,json
from pathlib import Path
from datetime import datetime,timezone
from .config import ROOT,environment
from .workspace import *
from .checkpoints import Budget,lock,restore,commit
from .models import DiagramSpec,AuthorResult
from .dataset import prepare_input
from .codex_runner import invoke,usage_from_events
from .executor import execute_build,validate_and_render
from .critic import judge_candidate
from .feedback import diagnose
from .reporting import report
from .runtime import configure

def selection_key(x):
    return (bool(x.get('artifact_valid')),bool(x.get('internal_gate_pass')),x.get('internal_score') if x.get('internal_score') is not None else -1)

def select_best(current,new):
    return new if current is None or selection_key(new)>selection_key(current) else current

def copy_input(input_dir,work):
    if not (work/'input').exists():shutil.copytree(input_dir,work/'input')

def source_files(source):
    return [p for p in source.rglob('*') if p.is_file() and '.harness' not in p.parts and '__pycache__' not in p.parts]

def finalize_task(task_dir,task_id,status,reason,best,candidates,budget,env):
    final=task_dir/'final';final.mkdir(exist_ok=True)
    if best and best['artifact_valid']:
        c=task_dir/'candidates'/best['candidate_id']
        shutil.copy2(c/'validated/reconstruction.pptx',final/'reconstruction.pptx')
        shutil.copy2(c/'render/screenshot.png',final/'screenshot.png')
        import zipfile
        with zipfile.ZipFile(final/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p in source_files(c/'source'):z.write(p,p.relative_to(c/'source'))
    evaluation_complete=status not in ('INFRA_ERROR','CONFIG_ERROR','INPUT_ERROR','CANCELLED') and bool(candidates) and all(x.get('evaluation_complete') for x in candidates)
    score=best.get('internal_score') if best else (0 if evaluation_complete else None)
    if not evaluation_complete:score=None
    usages=[usage_from_events(p) for p in task_dir.rglob('events.jsonl')]
    known=[u for u in usages if u is not None]
    usage={k:sum(u.get(k,0) for u in known) for k in set().union(*(u.keys() for u in known))} if known and len(known)==len(usages) and budget.usage_complete else None
    result={'schema_version':1,'task_id':task_id,'status':status,'quality_pass':status=='QUALITY_PASS',
            'selected_candidate':best['candidate_id'] if best else None,'artifact_valid':bool(best and best['artifact_valid']),
            'evaluation_complete':evaluation_complete,'internal_gate_pass':bool(best and best['internal_gate_pass']) if evaluation_complete else None,
            'internal_score':score,'judge_protocol':env.get('judge_protocol','astra_internal_v1'),'agent':env.get('agent'),'candidate_count':len(candidates),
            'agent_calls':budget.calls,'elapsed_seconds':budget.elapsed,'usage':usage,'cost_usd':None,
            'stop_reason':reason,'environment_fingerprint':env['fingerprint'],'official_comparable':False,
            'initial_score':candidates[0].get('internal_score') if candidates else None,
            'artifacts':{p.name:sha(p) for p in final.iterdir() if p.is_file() and p.name!='result.json'}}
    atomic_json(final/'result.json',result);budget.save();return result

async def run_task(run,task_id,config,env,inspect_pptx=None):
    task_dir=run/'tasks'/task_id;task_dir.mkdir(parents=True,exist_ok=True)
    with lock(task_dir/'task.lock'):
        existing=task_dir/'final/result.json'
        if existing.exists():
            old=read_json(existing)
            if old['status'] not in ('INFRA_ERROR','CANCELLED'):return old
        budget=Budget(task_dir/'budget.json',config['loop']);candidates=[];best=None;stalled=0
        status='BUDGET_EXHAUSTED';reason='Maximum candidate count reached';pending=None
        try:
            input_dir=task_dir/'input'
            task=prepare_input(config,task_id,input_dir)
            inputs=snapshot_hashes(input_dir)
            checkpoint=task_dir/'input-hashes.json'
            if checkpoint.exists() and read_json(checkpoint)!=inputs:raise ConfigError('Input changed since previous execution')
            atomic_json(checkpoint,inputs)
            if inspect_pptx is None:
                w=task_dir/'understanding';w.mkdir(exist_ok=True);copy_input(input_dir,w)
                spec=await invoke(config,budget,w,(ROOT/'prompts/understand.txt').read_text(),DiagramSpec.model_json_schema(),[w/'input/reference.png'],DiagramSpec.model_validate)
                if spec['task_id']!=task_id:raise HarnessError('Understanding task_id mismatch')
                atomic_json(task_dir/'diagram-spec.json',spec)
            for index in range(1 if inspect_pptx else config['loop']['max_candidates']):
                budget.check();cid=f'{index:03d}';c=task_dir/'candidates'/cid;c.mkdir(parents=True,exist_ok=True)
                complete=restore(c/'candidate.complete.json')
                if complete is None:
                    print(f'{task_id} candidate {cid}: author/execute/validate',flush=True)
                    source=c/'source';source.mkdir(exist_ok=True)
                    if inspect_pptx:
                        raw=c/'raw';raw.mkdir(exist_ok=True);shutil.copy2(inspect_pptx,raw/'reconstruction.pptx');atomic_json(raw/'object-map.json',[])
                        build={'valid_output':True}
                    else:
                        authored=restore(c/'author.complete.json')
                        if authored is None:
                            if best and best['artifact_valid']:
                                parent=task_dir/'candidates'/best['candidate_id']
                                feedback_path=parent/'feedback.json'
                                if not feedback_path.exists():await diagnose(parent,input_dir,config,budget)
                                feedback=read_json(feedback_path)
                                if feedback['candidate_id']!=parent.name:raise ConfigError('Feedback does not match parent')
                                for p in source_files(parent/'source'):
                                    dst=source/p.relative_to(parent/'source');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
                                atomic_json(source/'feedback.json',feedback)
                            elif index>0:
                                prev=task_dir/'candidates'/f'{index-1:03d}'
                                for p in source_files(prev/'source'):
                                    dst=source/p.relative_to(prev/'source');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
                                errors={str(p.relative_to(prev)):p.read_text(errors='replace')[-12000:] for p in list(prev.glob('raw/*.log'))+list(prev.glob('artifact-report.json'))}
                                atomic_json(source/'feedback.json',{'candidate_id':prev.name,'action':'revise','errors':errors})
                            copy_input(input_dir,source)
                            if not (source/'diagram-spec.json').exists():shutil.copy2(task_dir/'diagram-spec.json',source/'diagram-spec.json')
                            if not (source/'native').exists():shutil.copytree(ROOT/'src/pptbench_harness/native',source/'native',ignore=shutil.ignore_patterns('__pycache__'))
                            role='repair' if index else 'author'
                            payload=await invoke(config,budget,source,(ROOT/'prompts'/f'{role}.txt').read_text(),AuthorResult.model_json_schema(),[source/'input/reference.png'],AuthorResult.model_validate)
                            inside(source,payload['spec_path'])
                            if not (source/'build.py').is_file():raise HarnessError('Author omitted build.py')
                            snapshot_hashes(source)
                            if snapshot_hashes(source/'input')!=inputs:raise HarnessError('Author modified protected inputs')
                            commit(c/'author.complete.json',payload,source_files(source))
                        build=await execute_build(source,c/'raw',config,budget)
                    valid=False;score=0;gate=False;evaluated=True
                    if build['valid_output']:
                        artifact=await validate_and_render(c,input_dir,config,budget);valid=artifact['valid']
                        if valid:
                            pending={'candidate_id':cid,'artifact_valid':True,'internal_gate_pass':False,'internal_score':None,'evaluation_complete':False}
                            print(f'{task_id} candidate {cid}: three-round Codex judge',flush=True)
                            merged=await judge_candidate(c,task_id,input_dir,config,budget)
                            score=merged['total_score'];gate=not merged['majority_gate']
                    complete={'candidate_id':cid,'artifact_valid':valid,'internal_gate_pass':gate,'internal_score':score,'evaluation_complete':evaluated}
                    files=[c/'raw/reconstruction.pptx'] if (c/'raw/reconstruction.pptx').exists() else []
                    if (c/'consensus.json').exists():files.append(c/'consensus.json')
                    commit(c/'candidate.complete.json',complete,files)
                pending=None
                candidates.append(complete);new=select_best(best,complete)
                if best is not None:stalled=0 if new is not best else stalled+1
                best=new
                atomic_json(task_dir/'checkpoint.json',{'best':best,'candidates':candidates,'no_improvement':stalled})
                print(f'{task_id} candidate {cid}: valid={complete["artifact_valid"]}, score={complete["internal_score"]}',flush=True)
                if best['artifact_valid'] and best['internal_gate_pass'] and best['internal_score']>=config['loop']['target_internal_score']:
                    status='QUALITY_PASS';reason='All internal completion conditions met';break
                if inspect_pptx:status='INSPECTED';reason='Inspection complete';break
                if stalled>=config['loop']['max_no_improvement']:status='STALLED';reason='Consecutive candidates did not improve';break
            if not best or not best['artifact_valid']:status='NO_VALID_ARTIFACT';reason='No valid rendered candidate produced'
        except BudgetExhausted as exc:status=exc.kind;reason=str(exc)
        except (HarnessError,OSError,ValueError) as exc:status=getattr(exc,'kind','INFRA_ERROR');reason=str(exc)
        except (asyncio.CancelledError,KeyboardInterrupt):
            if pending:
                candidates.append(pending);best=select_best(best,pending)
            finalize_task(task_dir,task_id,'CANCELLED','Interrupted; resume supported',best,candidates,budget,env);raise
        if pending:
            candidates.append(pending);best=select_best(best,pending)
        result=finalize_task(task_dir,task_id,status,reason,best,candidates,budget,env)
        return result

async def run_batch(config,ids,run_dir=None,inspect_pptx=None):
    env=environment(config)
    if run_dir is None:
        run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
        run=Path(config['output']['root'])/run_id;run.mkdir(parents=True)
        atomic_json(run/'resolved-config.json',config);atomic_json(run/'environment.json',env)
        atomic_json(run/'manifest.json',{'tasks':ids,'inspect_pptx':str(inspect_pptx) if inspect_pptx else None})
        import zipfile
        with zipfile.ZipFile(run/'implementation-snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
            for folder in ['src/pptbench_harness','prompts','schemas']:
                for p in (ROOT/folder).rglob('*'):
                    if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT))
    else:
        run=run_dir
        old_env=read_json(run/'environment.json')
        if old_env['fingerprint']!=env['fingerprint']:raise ConfigError('Environment/prompt/implementation changed; start new run')
        if read_json(run/'resolved-config.json')!=config:raise ConfigError('Frozen configuration changed')
        manifest=read_json(run/'manifest.json');ids=manifest['tasks'];inspect_pptx=Path(manifest['inspect_pptx']) if manifest.get('inspect_pptx') else None
    print(f'RUN_DIR={run}',flush=True)
    configure(config)
    sem=asyncio.Semaphore(config['execution']['task_concurrency']);fatal=asyncio.Event()
    async def one(task_id):
        async with sem:
            if fatal.is_set():return
            result=await run_task(run,task_id,config,env,inspect_pptx)
            report(run)
            if result['status']=='CONFIG_ERROR':fatal.set()
    await asyncio.gather(*(one(task_id) for task_id in ids))
    return run,report(run)
