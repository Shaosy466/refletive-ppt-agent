import asyncio,json
from pathlib import Path
from pptbench_harness.codex_runner import invoke
from pptbench_harness.checkpoints import Budget
from pptbench_harness.config import load_config
from pptbench_harness.workspace import HarnessError
import pytest

def fake_cli(tmp_path,return_code=0,valid=True):
    p=tmp_path/'fake-codex'
    p.write_text('#!/usr/bin/env python3\nimport sys,json,pathlib\n'
                 'a=sys.argv\n'
                 f'pathlib.Path(a[a.index("--output-last-message")+1]).write_text({repr(json.dumps({"answer":"ok"}) if valid else "not json")})\n'
                 'print(json.dumps({"type":"future.event","other":42}))\n'
                 'print(json.dumps({"type":"turn.completed","usage":{"input_tokens":11,"output_tokens":2}}))\n'
                 f'sys.exit({return_code})\n')
    p.chmod(0o755);return str(p)

def test_runner_resume_does_not_call_again(tmp_path):
    config=load_config();config['agent']['executable']=fake_cli(tmp_path)
    budget=Budget(tmp_path/'budget.json',config['loop'])
    schema={'type':'object','properties':{'answer':{'type':'string'}},'required':['answer'],'additionalProperties':False}
    work=tmp_path/'work'
    first=asyncio.run(invoke(config,budget,work,'test',schema));assert first=={'answer':'ok'}
    assert budget.calls==1
    assert asyncio.run(invoke(config,budget,work,'test',schema))==first
    assert budget.calls==1

def test_malformed_and_exit_failures(tmp_path):
    config=load_config();config['agent']['executable']=fake_cli(tmp_path,valid=False)
    budget=Budget(tmp_path/'budget.json',config['loop'])
    with pytest.raises(HarnessError,match='AGENT_OUTPUT_ERROR'):
        asyncio.run(invoke(config,budget,tmp_path/'work','test',{'type':'object'}))
    config['agent']['executable']=fake_cli(tmp_path,return_code=7)
    with pytest.raises(HarnessError,match='exited 7'):
        asyncio.run(invoke(config,budget,tmp_path/'work2','test',{'type':'object'}))

def test_bounded_format_repair_preserves_original(tmp_path,monkeypatch):
    from pptbench_harness.models import Probe
    calls=[]
    async def fake(argv,cwd,stdout,stderr,timeout,stdin=None,extra_env=None):
        calls.append(str(cwd))
        payload={'labels':['A'],'wrote_file':True} if cwd.name=='format-repair' else {'labels':['A']}
        Path(argv[argv.index('--output-last-message')+1]).write_text(json.dumps(payload))
        stdout.write_text('{"type":"turn.completed","usage":{"input_tokens":1}}\n');stderr.write_text('');return 0
    monkeypatch.setattr('pptbench_harness.codex_runner.process',fake)
    c=load_config();b=Budget(tmp_path/'budget.json',c['loop'])
    result=asyncio.run(invoke(c,b,tmp_path/'work','test',Probe.model_json_schema(),validator=Probe.model_validate))
    assert result['wrote_file'] and len(calls)==2 and b.calls==2
    raw=json.loads((tmp_path/'work/.harness/attempt-00/response.json').read_text())
    assert 'wrote_file' not in raw
    assert (tmp_path/'work/.harness/attempt-00/corrected-response.json').exists()

def test_plugin_catalog_401_is_not_model_auth_failure(tmp_path,monkeypatch):
    from pptbench_harness.workspace import ConfigError
    async def fake(argv,cwd,stdout,stderr,timeout,stdin=None,extra_env=None):
        stdout.write_text(json.dumps({'type':'error','message':'invalid_request_error'})+'\n')
        stderr.write_text('Plugin catalog request returned 401 Unauthorized')
        return 1
    monkeypatch.setattr('pptbench_harness.codex_runner.process',fake)
    c=load_config();b=Budget(tmp_path/'budget.json',c['loop'])
    with pytest.raises(HarnessError,match='exited 1') as err:
        asyncio.run(invoke(c,b,tmp_path/'work','test',{'type':'object'}))
    assert not isinstance(err.value,ConfigError)
