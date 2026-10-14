from pathlib import Path
from pptbench_harness.orchestrator import finalize_task
from pptbench_harness.checkpoints import Budget
from pptbench_harness.config import load_config

def test_incomplete_judge_preserves_valid_artifact(tmp_path):
    c=load_config();candidate=tmp_path/'candidates/000'
    for folder in ['validated','render','source']:(candidate/folder).mkdir(parents=True)
    (candidate/'validated/reconstruction.pptx').write_bytes(b'fixture')
    (candidate/'render/screenshot.png').write_bytes(b'fixture')
    (candidate/'source/build.py').write_text('pass')
    best={'candidate_id':'000','artifact_valid':True,'internal_gate_pass':False,'internal_score':None,'evaluation_complete':False}
    b=Budget(tmp_path/'budget.json',c['loop'])
    result=finalize_task(tmp_path,'task_0004','INFRA_ERROR','judge disconnected',best,[best],b,{'fingerprint':'test'})
    assert result['internal_score'] is None
    assert result['artifact_valid'] is True
    assert result['evaluation_complete'] is False
    assert (tmp_path/'final/reconstruction.pptx').read_bytes()==b'fixture'
