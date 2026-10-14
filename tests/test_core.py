import asyncio,json,sys
from pathlib import Path
import pytest
from PIL import Image
from pptbench_harness.config import load_config
from pptbench_harness.codex_runner import command,process,usage_from_events
from pptbench_harness.workspace import inside,InputError,atomic_json,ConfigError,BudgetExhausted
from pptbench_harness.checkpoints import Budget,commit,restore,lock
from pptbench_harness.models import Feedback
from pptbench_harness.orchestrator import select_best
from pptbench_harness.upstream_adapter import score_round,consensus
from pptbench_harness.native import NativeSlide
from eval_harness.pptx import validate_reconstruction_pptx,render_pptx,PptxError

def test_fixed_model():
    c=load_config();a=command(c,Path('/tmp/x'),Path('s'),Path('r'),[])
    assert a[a.index('--model')+1]=='gpt-6-astra'
    assert 'model_reasoning_effort="high"' in a

def test_path_escape(tmp_path):
    for p in ('../outside','/etc/passwd'):
        with pytest.raises(InputError):inside(tmp_path,p)
    (tmp_path/'link').symlink_to('/tmp')
    with pytest.raises(InputError):inside(tmp_path,'link/file')

def test_feedback_schema():
    data={'schema_version':1,'candidate_id':'000','action':'explore','issues':[],'preserve_ids':[],'reason':'zoom',
          'explore_requests':[{'image':'candidate','bbox':[0.9,0,0.5,0.1],'scale':2,'reason':'x'}]}
    with pytest.raises(ValueError):Feedback.model_validate(data)
    data['explore_requests']=[];data['extra']=True
    with pytest.raises(ValueError):Feedback.model_validate(data)

def gated(round_id,stage):
    _,r=score_round('task_0004','000',round_id,{stage:{'status':'complete','output':{'gate_keeper':{'triggered':True,'reason':'wrong arrow'}}}},stage)
    return r

def test_mixed_stage_majority():
    a=gated(1,'semantic_gate');b=gated(2,'render_gate');c=gated(3,'semantic_gate')
    c['gate_keeper']['triggered']=False;c['source_final_status']='scored'
    result=consensus([a,b,c]);assert result['majority_gate'];assert result['total_score']==0
    with pytest.raises(ValueError):consensus([a,a,c])

def test_best_rollback():
    a={'artifact_valid':True,'internal_gate_pass':True,'internal_score':90}
    b={'artifact_valid':True,'internal_gate_pass':False,'internal_score':0}
    assert select_best(a,b) is a
    assert select_best(a,dict(a)) is a

def test_budget_checkpoint_lock(tmp_path):
    b=Budget(tmp_path/'budget.json',{'task_timeout_seconds':100,'max_agent_calls':1});b.begin(5);b.finish()
    with pytest.raises(BudgetExhausted):b.begin(5)
    f=tmp_path/'a';f.write_text('one');commit(tmp_path/'done.json',{'ok':1},[f]);assert restore(tmp_path/'done.json')=={'ok':1}
    f.write_text('two')
    with pytest.raises(ConfigError):restore(tmp_path/'done.json')
    with lock(tmp_path/'lock'):
        with pytest.raises(ConfigError):
            with lock(tmp_path/'lock'):pass

def test_usage_missing(tmp_path):
    p=tmp_path/'events';p.write_text('{"type":"unknown"}\n');assert usage_from_events(p) is None
    p.write_text('{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":4}}\n');assert usage_from_events(p)['input_tokens']==12

def test_process_timeout(tmp_path):
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(process([sys.executable,'-c','import time;time.sleep(10)'],tmp_path,tmp_path/'out',tmp_path/'err',0.1))

def test_native_render_and_invalid(tmp_path):
    s=NativeSlide();s.rect('A',[.1,.4,.2,.15],'Input');s.rect('B',[.6,.4,.2,.15],'Output');s.edge('e',[(.3,.475),(.6,.475)])
    p=tmp_path/'native.pptx';s.save(p,tmp_path/'map.json')
    validate_reconstruction_pptx(p,approved_resource_paths=[])
    render_pptx(p,tmp_path/'render.png',soffice_command=load_config()['execution']['soffice'])
    assert Image.open(tmp_path/'render.png').size==(1600,900)
    s.prs.slides.add_slide(s.prs.slide_layouts[6]);s.save(tmp_path/'two.pptx',tmp_path/'map2.json')
    with pytest.raises(PptxError):validate_reconstruction_pptx(tmp_path/'two.pptx',approved_resource_paths=[])
    (tmp_path/'bad.pptx').write_text('invalid')
    with pytest.raises(PptxError):validate_reconstruction_pptx(tmp_path/'bad.pptx',approved_resource_paths=[])

def test_sleep_aware_clock_monotonic():
    from pptbench_harness.checkpoints import clock
    import time
    start=clock();time.sleep(.01);assert clock()>start
