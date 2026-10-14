import asyncio
import json
from pathlib import Path
import pytest
from pptbench_harness.config import load_config
from pptbench_harness.codex_runner import command, invoke
from pptbench_harness.checkpoints import Budget
from pptbench_harness.workspace import ConfigError, atomic_json
from pptbench_harness.upstream_adapter import score_round
from pptbench_harness.reporting import report
from pptbench_harness.replay import fork_generation


def test_custom_model_config_and_command(tmp_path):
    source=Path('configs/default.toml').read_text()
    cfg=tmp_path/'config.toml'
    cfg.write_text(source.replace('gpt-6-astra','my-codex-model').replace('reasoning_effort = "high"','reasoning_effort = "medium"'))
    c=load_config(cfg)
    argv=command(c,tmp_path,tmp_path/'schema',tmp_path/'response',[])
    assert argv[argv.index('--model')+1]=='my-codex-model'
    assert 'model_reasoning_effort="medium"' in argv
    cfg.write_text(source.replace('gpt-6-astra','bad model'))
    with pytest.raises(ConfigError): load_config(cfg)


def test_model_identity_in_requests_and_cache(tmp_path,monkeypatch):
    c=load_config();c['agent'].update(model='my-codex-model',reasoning_effort='medium')
    async def fake(argv,cwd,stdout,stderr,timeout,stdin=None):
        Path(argv[argv.index('--output-last-message')+1]).write_text('{"ok":true}')
        stdout.write_text('');stderr.write_text('');return 0
    monkeypatch.setattr('pptbench_harness.codex_runner.process',fake)
    budget=Budget(tmp_path/'budget.json',c['loop']);work=tmp_path/'work'
    asyncio.run(invoke(c,budget,work,'test',{'type':'object'}))
    request=json.loads((work/'.harness/attempt-00/request.json').read_text())
    assert request['requested_model']=='my-codex-model'
    assert request['reasoning_effort']=='medium'
    c['agent']['model']='another-model'
    with pytest.raises(ConfigError):asyncio.run(invoke(c,budget,work,'test',{'type':'object'}))


def test_scoring_and_report_record_actual_model(tmp_path):
    raw,ranked=score_round('task_0004','000',1,{'semantic_gate':{'status':'complete','output':{'gate_keeper':{'triggered':True,'reason':'wrong arrow'}}}},'semantic_gate','my-codex-model','medium')
    assert raw['judge_model']=='my-codex-model'
    assert ranked['judge_model']=='my-codex-model'
    assert raw['judge_effort']=='medium'
    assert raw['protocol_id']=='codex_internal_v1'
    atomic_json(tmp_path/'manifest.json',{'tasks':['task_0004']})
    atomic_json(tmp_path/'environment.json',{'agent':{'model':'my-codex-model','reasoning_effort':'medium'},'judge_protocol':'codex_internal_v1'})
    r=report(tmp_path)
    assert r['agent']['model']=='my-codex-model'
    assert r['judge_protocol']=='codex_internal_v1'


def test_replay_rejects_model_change_before_reuse(tmp_path):
    c=load_config()
    atomic_json(tmp_path/'manifest.json',{'tasks':[]})
    atomic_json(tmp_path/'resolved-config.json',c)
    c['agent']['model']='another-model'
    with pytest.raises(ConfigError,match='original model'):fork_generation(tmp_path,c)
