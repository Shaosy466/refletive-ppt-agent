import asyncio,json,sys
from pathlib import Path
import pytest
from reflective_harness.artifacts import safe_path,manifest,verify,evidence
from reflective_harness.contracts import Task,Execution,Evaluation,Review
from reflective_harness.controller import run_artifact
from reflective_harness.registry import discover,get
from reflective_harness.command_adapter import CommandSpec,CommandAdapter


def test_registry_deduplicates_code4scene(tmp_path):
    entries=discover()
    assert len(entries)==10
    assert list(entries).count('code4scene')==1
    assert get('code4scene',tmp_path).doctor()['ready'] is False


def test_paths_and_frozen_candidate(tmp_path):
    for relative in ('../private','/private'):
        with pytest.raises(ValueError):safe_path(tmp_path,relative)
    (tmp_path/'x').symlink_to('/tmp')
    with pytest.raises(ValueError):safe_path(tmp_path,'x/anything')
    (tmp_path/'x').unlink();(tmp_path/'a').write_text('first')
    expected=manifest(tmp_path);(tmp_path/'a').write_text('tampered')
    with pytest.raises(ValueError):verify(tmp_path,expected)


def test_loop_final_score_is_never_feedback(tmp_path):
    public=tmp_path/'public';public.mkdir();(public/'input.txt').write_text('public requirement')
    task=Task(benchmark='test',case_id='one',revision='v1',instruction='Produce a result',public_dir=str(public),output_contract='result.txt')
    config={'agent':{'model':'test','reasoning_effort':'high'},'loop':{'max_candidates':2,'task_timeout_seconds':30,'max_agent_calls':4}}
    prompts=[];author_calls=0
    async def fake_agent(config,budget,work,prompt,schema,images=()):
        nonlocal author_calls
        prompts.append(prompt)
        if 'author/repairer' in prompt:
            author_calls+=1;(work/'result.txt').write_text(str(author_calls))
            return {'summary':'written','outputs':['result.txt']}
        return Review(decision='revise' if author_calls==1 else 'done',findings=[],summary='public review').model_dump()
    class Adapter:
        async def execute(self,task,work,output,cid):
            (output/'log.txt').write_text('public execution')
            return Execution(ok=True,evidence=[evidence(output/'log.txt',output,'log',cid)])
        async def evaluate(self,task,submission,output):
            assert (submission/'result.txt').read_text()=='2'
            return Evaluation(complete=True,protocol='test',details={'secret':'HIDDEN_SCORE_73'})
    out=tmp_path/'run'
    result=asyncio.run(run_artifact(Adapter(),task,config,out,fake_agent))
    assert result['status']=='complete' and author_calls==2
    assert all('HIDDEN_SCORE_73' not in p for p in prompts)
    assert asyncio.run(run_artifact(Adapter(),task,config,out,fake_agent))==result
    assert author_calls==2
    (out/'submission/result.txt').write_text('modified')
    with pytest.raises(ValueError):asyncio.run(run_artifact(Adapter(),task,config,out,fake_agent))


def test_command_timeout_and_missing_evidence(tmp_path):
    public=tmp_path/'public';public.mkdir()
    task=Task(benchmark='test',case_id='one',revision='v1',instruction='test',public_dir=str(public),output_contract='image')
    adapter=CommandAdapter(CommandSpec(task=task,execute=[sys.executable,'-c','print("ok")'],evaluate=[sys.executable,'-c','pass'],evidence_files={'missing.png':'image'}))
    out=tmp_path/'ev';out.mkdir()
    result=asyncio.run(adapter.execute(task,public,out,'001'))
    assert not result.ok and result.public_feedback['missing_evidence']==['missing.png']
    final=tmp_path/'final';final.mkdir()
    assert not asyncio.run(adapter.evaluate(task,public,final)).complete

def test_resume_after_review_failure_reuses_candidate_and_execution(tmp_path):
    public=tmp_path/'public';public.mkdir();(public/'input.txt').write_text('public')
    task=Task(benchmark='test',case_id='one',revision='v1',instruction='Produce a file',public_dir=str(public),output_contract='a.txt')
    config={'agent':{'model':'test','reasoning_effort':'high'},'loop':{'max_candidates':1,'task_timeout_seconds':30,'max_agent_calls':4}}
    calls={'author':0,'execute':0,'review':0}
    async def agent(config,budget,work,prompt,schema,images=()):
        if 'author/repairer' in prompt:
            calls['author']+=1;(work/'a.txt').write_text('candidate')
            return {'summary':'done','outputs':['a.txt']}
        calls['review']+=1
        if calls['review']==1:raise RuntimeError('transient review failure')
        assert (work/'candidate/a.txt').read_text()=='candidate'
        return Review(decision='done',findings=[],summary='observed').model_dump()
    class Adapter:
        async def execute(self,task,work,out,cid):
            calls['execute']+=1;(out/'log').write_text('executed')
            return Execution(ok=True,evidence=[evidence(out/'log',out,'log',cid)])
        async def evaluate(self,*args):return Evaluation(complete=True,protocol='test')
    run=tmp_path/'run'
    with pytest.raises(RuntimeError):asyncio.run(run_artifact(Adapter(),task,config,run,agent))
    result=asyncio.run(run_artifact(Adapter(),task,config,run,agent))
    assert result['status']=='complete'
    assert calls=={'author':1,'execute':1,'review':2}
