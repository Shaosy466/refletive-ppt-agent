import asyncio,json
from pathlib import Path
from pptbench_harness.config import load_config
from pptbench_harness.runtime import configure
from pptbench_harness.checkpoints import Budget
from pptbench_harness.codex_runner import invoke
from pptbench_harness.workspace import atomic_json
from pptbench_harness.reporting import report

def test_shared_agent_concurrency(tmp_path,monkeypatch):
    c=load_config();c['execution']['agent_concurrency']=2
    active=0;peak=0
    async def fake(argv,cwd,stdout,stderr,timeout,stdin=None):
        nonlocal active,peak
        active+=1;peak=max(peak,active)
        await asyncio.sleep(.03)
        Path(argv[argv.index('--output-last-message')+1]).write_text('{"ok":true}')
        stdout.write_text('{"type":"turn.completed","usage":{"input_tokens":1}}\n');stderr.write_text('')
        active-=1;return 0
    monkeypatch.setattr('pptbench_harness.codex_runner.process',fake)
    async def exercise():
        configure(c)
        async def one(i):
            return await invoke(c,Budget(tmp_path/f'b{i}.json',c['loop']),tmp_path/f'w{i}','test',{'type':'object'})
        await asyncio.gather(*(one(i) for i in range(5)))
    asyncio.run(exercise());assert peak==2

def test_report_missing_tasks_not_dropped(tmp_path):
    atomic_json(tmp_path/'manifest.json',{'tasks':['task_0001','task_0004']})
    atomic_json(tmp_path/'tasks/task_0001/final/result.json',{'task_id':'task_0001','evaluation_complete':True,
        'artifact_valid':True,'internal_gate_pass':True,'internal_score':95,'agent_calls':9,'elapsed_seconds':100,
        'status':'QUALITY_PASS','selected_candidate':'000','stop_reason':'passed'})
    r=report(tmp_path)
    assert r['mean_score'] is None
    assert r['completed_subset_mean']==95
    assert r['evaluation_incomplete_count']==1
