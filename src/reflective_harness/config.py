from pathlib import Path
import shutil,tomllib
ROOT=Path(__file__).resolve().parents[2]

def load_config(path=None):
    d=tomllib.loads(Path(path or ROOT/'configs/multimodal.toml').read_text())
    if d.get('schema_version')!=1:raise ValueError('Unknown config schema')
    a=d['agent'];loop=d['loop']
    if not isinstance(a['model'],str) or not a['model'].strip() or a['model'].startswith('-') or any(c.isspace() for c in a['model']):raise ValueError('Invalid Codex model ID')
    if a['reasoning_effort'] not in ('minimal','low','medium','high','xhigh'):raise ValueError('Invalid effort')
    if a['sandbox']!='workspace-write':raise ValueError('Only workspace-write development mode is supported')
    if a['max_transport_retries'] not in (0,1):raise ValueError('Invalid transport retry limit')
    if a['call_timeout_seconds']<=0:raise ValueError('Invalid call timeout')
    for key in ('max_candidates','max_agent_calls','task_timeout_seconds'):
        if loop[key]<1:raise ValueError('Invalid budget '+key)
    a['executable']=shutil.which(a['executable'])
    if not a['executable']:raise ValueError('Codex executable not found')
    return d
