"""Artifact loop: explicit context, immutable candidates, final score after freeze.

Local-development runner, not a security boundary. Benchmark workers must provide
isolation before results can be considered official-protocol comparable.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from pptbench_harness.codex_runner import invoke
from pptbench_harness.checkpoints import Budget, lock
from pptbench_harness.workspace import atomic_json
from .contracts import Review, Execution, strict_schema
from .artifacts import manifest, snapshot, identity, verify, safe_path, sha

class AuthorResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str
    outputs: list[str]

async def run_artifact(adapter, task, config, run_dir: Path, agent=invoke):
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True,exist_ok=True)
    signature = identity({'task':task.model_dump(),'config':config,'public':manifest(Path(task.public_dir))})
    with lock(run_dir/'lock'):
        checkpoint = run_dir/'run.json'
        if checkpoint.exists():
            old=json.loads(checkpoint.read_text())
            if old['signature'] != signature: raise ValueError('Run inputs changed; create a new run')
            if old['status']=='complete':
                verify(run_dir/'submission',old['submission_manifest'])
                return json.loads((run_dir/'result.json').read_text())
            if (run_dir/'freeze.json').exists():raise ValueError('Frozen run needs evaluation recovery; not implemented')
            stages=list((run_dir/'stages').glob('*'))
            if not stages or any(not (p/'execution.json').exists() for p in stages):
                raise ValueError('Recovery requires a completed execution checkpoint; partial engine actions are not replayed')
        atomic_json(checkpoint,{'signature':signature,'status':'running','task':task.model_dump()})
        atomic_json(run_dir/'config.json',config)
        budget=Budget(run_dir/'budget.json',config['loop'])
        current=run_dir/'workspace'
        if not current.exists():shutil.copytree(task.public_dir,current)
        feedback={}
        last=None
        try:
            for i in range(config['loop']['max_candidates']):
                budget.check()
                cid=f'{i:03d}'
                stage=run_dir/'stages'/cid;stage.mkdir(parents=True,exist_ok=True)
                if (stage/'execution.json').exists():
                    candidate=run_dir/'candidates'/cid
                    files=json.loads((stage/'candidate.json').read_text())['files']
                    verify(candidate,files)
                    execution=Execution.model_validate_json((stage/'execution.json').read_text())
                    evdir=stage/'evidence'
                else:
                    # One Codex conversation per role, explicit persisted input each time.
                    prompt=('You are the author/repairer in a multimodal benchmark harness. Work only in this workspace. '
                            'Do not inspect sibling directories, benchmark solutions, tests, or hidden scoring data. '
                            'Edit the actual deliverable; do not only describe it. Preserve unrelated working behavior.\n'
                            +json.dumps({'task':task.model_dump(exclude={'public_dir'}),'feedback':feedback},ensure_ascii=False))
                    # Avoid stale author-cache reuse when revising the same workspace.
                    if (current/'.harness').exists(): shutil.move(current/'.harness',stage/'previous-author-cache')
                    public_images=sorted(p for p in current.glob('target-*.png'))
                    answer=await agent(config,budget,current,prompt,AuthorResponse.model_json_schema(),public_images)
                    for output in answer['outputs']: safe_path(current,output)
                    atomic_json(stage/'author.json',answer)
                    if (current/'.harness').exists(): shutil.move(current/'.harness',stage/'author-call')
                    candidate=run_dir/'candidates'/cid
                    candidate.parent.mkdir(exist_ok=True)
                    files=snapshot(current,candidate)
                    candidate_hash=identity(files)
                    atomic_json(stage/'candidate.json',{'id':cid,'hash':candidate_hash,'files':files,'parent':last})
                    evdir=stage/'evidence';evdir.mkdir()
                    # Execute a disposable copy, not the frozen source.
                    execution_dir=stage/'execution';shutil.copytree(candidate,execution_dir)
                    execution=await adapter.execute(task,execution_dir,evdir,cid)
                    atomic_json(stage/'execution.json',execution.model_dump())
                for exploration in range(2):
                    review_dir=stage/('review' if exploration==0 else f'review-{exploration}');review_dir.mkdir(exist_ok=True)
                    shutil.copytree(candidate,review_dir/'candidate',dirs_exist_ok=True)
                    images=[]
                    for item in execution.evidence:
                        p=safe_path(evdir,item.path)
                        if sha(p)!=item.sha256 or item.candidate_id!=cid: raise ValueError('Stale evidence')
                        dest=review_dir/'evidence'/item.path;dest.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(p,dest)
                        if item.kind=='image':images.append(dest)
                    review_prompt=('Observe the attached actual execution evidence and diagnose this candidate against the public task. '
                        'Never accept the author summary as proof. Reference evidence paths in every finding. '
                        'If evidence is missing request explore; if defective request revise. Do not change files or read outside this directory. '
                        'Read candidate/ for current submitted source and public requirements (GDD.md/TASK.txt when present). '
                        'Each findings.evidence MUST be a list of exact paths from execution.evidence[].path, e.g. initial.png; '
                        'do not prepend evidence/, append line numbers or prose, or put source paths in that list. '
                        'Put source locations and explanations in observed/repair instead. This is public self-check, not an official score.\n'+json.dumps({'task':task.model_dump(exclude={'public_dir'}),'execution':execution.model_dump()},ensure_ascii=False))
                    review_result=stage/('review.json' if exploration==0 else f'review-{exploration}.json')
                    if review_result.exists():
                        raw=json.loads(review_result.read_text())
                    else:
                        raw=await agent(config,budget,review_dir,review_prompt,strict_schema(Review),images)
                    review=Review.model_validate(raw)
                    known={e.path for e in execution.evidence}
                    for finding in review.findings:
                        if not finding.evidence or not set(finding.evidence)<=known: raise ValueError('Finding has no valid evidence')
                    atomic_json(review_result,review.model_dump())
                    verify(candidate,files)
                    if review.decision!='explore' or exploration==1:break
                    evdir=stage/'explore-evidence';evdir.mkdir(exist_ok=True)
                    execution_dir=stage/'explore-execution'
                    if not execution_dir.exists():shutil.copytree(candidate,execution_dir)
                    execution=await adapter.execute(task,execution_dir,evdir,cid)
                    atomic_json(stage/'explore-execution.json',execution.model_dump())
                last=cid
                feedback={'execution':execution.public_feedback,'review':review.model_dump()}
                # Explore is not silently treated as successful. Further evidence support
                # is adapter-specific; this version ends with an explicit incomplete check.
                if review.decision in ('done','explore'):break
            submission=run_dir/'submission'
            frozen=snapshot(run_dir/'candidates'/last,submission)
            atomic_json(run_dir/'freeze.json',{'candidate':last,'files':frozen,'selection':'last_public_candidate'})
            final_dir=run_dir/'evaluation';final_dir.mkdir()
            evaluation=await adapter.evaluate(task,submission,final_dir)
            verify(submission,frozen)
            result={'schema_version':1,'benchmark':task.benchmark,'case_id':task.case_id,
                    'status':'complete' if evaluation.complete else 'evaluation_incomplete',
                    'candidate':last,'review_decision':review.decision,'execution_ok':execution.ok,
                    'evaluation':evaluation.model_dump(),'agent_calls':budget.calls,
                    'requested_model':config['agent']['model'],'reasoning_effort':config['agent']['reasoning_effort']}
            atomic_json(run_dir/'result.json',result)
            atomic_json(checkpoint,{'signature':signature,'status':'complete','task':task.model_dump(),'submission_manifest':frozen})
            return result
        except BaseException as exc:
            atomic_json(run_dir/'error.json',{'type':type(exc).__name__,'message':str(exc)})
            raise
        finally:budget.save()
