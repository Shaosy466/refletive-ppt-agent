from __future__ import annotations
import shutil, subprocess, sys, platform, tomllib
from pathlib import Path
from .workspace import ConfigError, digest, sha, tree_hash

ROOT = Path(__file__).resolve().parents[2]
COMMIT = 'd64c09f10a4376fa46532dc82048d1b5228e8b76'

def load_config(path=None):
    path = Path(path or ROOT/'configs/default.toml').resolve()
    d = tomllib.loads(path.read_text())
    if d.get('schema_version') != 1: raise ConfigError('Unknown config version')
    model = d['agent']['model']
    if not isinstance(model,str) or not model.strip() or model.startswith('-') or any(ch.isspace() for ch in model):
        raise ConfigError('Provide a nonempty Codex model ID without whitespace')
    if d['agent']['reasoning_effort'] not in ('minimal','low','medium','high','xhigh'):
        raise ConfigError('Unsupported reasoning effort; model support is checked by Codex')
    if d['loop']['judge_rounds'] != 3: raise ConfigError('Exactly three judge rounds required')
    if d['mode'] != 'local-dev': raise ConfigError('Benchmark isolation not enabled; use local-dev. No official comparability is claimed.')
    for key in ('max_candidates','max_no_improvement','max_agent_calls','task_timeout_seconds'):
        if d['loop'][key] < 1: raise ConfigError(f'Invalid loop limit: {key}')
    if not 0 <= d['loop']['target_internal_score'] <= 100: raise ConfigError('Invalid target score')
    if not 0 <= d['loop']['max_explore_per_candidate'] <= 2: raise ConfigError('At most 2 explorations')
    if any(not 1 <= d['execution'][x] <= 4 for x in ('task_concurrency','agent_concurrency')):
        raise ConfigError('Task and agent concurrency must be 1..4')
    if d['execution']['render_concurrency'] != 1: raise ConfigError('Render concurrency must be 1')
    if d['agent']['sandbox'] != 'workspace-write': raise ConfigError('Agent sandbox must be workspace-write')
    if d['agent']['call_timeout_seconds'] <= 0: raise ConfigError('Call timeout must be positive')
    if d['agent']['max_transport_retries'] not in (0,1): raise ConfigError('At most one transport retry')
    for section,key in [('dataset','root'),('dataset','upstream_root'),('output','root')]:
        p = Path(d[section][key]); d[section][key] = str((ROOT/p).resolve()) if not p.is_absolute() else str(p)
    executable = shutil.which(d['agent']['executable'])
    if not executable: raise ConfigError('Codex executable not found')
    d['agent']['executable'] = executable
    soffice = d['execution'].get('soffice') or shutil.which('soffice')
    mac = Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
    if not soffice and mac.exists(): soffice = str(mac)
    d['execution']['soffice'] = soffice
    d['execution']['fontconfig_file'] = str(ROOT/'configs/fonts-macos.conf') if platform.system()=='Darwin' else None
    return d

def environment(config, require_renderer=True):
    up = Path(config['dataset']['upstream_root'])
    actual = subprocess.check_output(['git','-C',str(up),'rev-parse','HEAD'],text=True).strip()
    if actual != COMMIT or config['dataset']['upstream_commit'] != COMMIT: raise ConfigError('Upstream commit mismatch')
    if subprocess.check_output(['git','-C',str(up),'status','--porcelain'],text=True).strip(): raise ConfigError('Upstream checkout modified')
    import eval_harness.pptx as upstream
    if not Path(upstream.__file__).resolve().is_relative_to(up): raise ConfigError('Wrong installed upstream package')
    soffice=config['execution']['soffice']
    if not soffice and require_renderer: raise ConfigError('LibreOffice missing')
    def version(cmd): return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT,timeout=20).strip()
    fonts={}
    for base in [Path('/System/Library/Fonts'),Path('/Library/Fonts'),Path.home()/'Library/Fonts',Path('/usr/share/fonts'),Path('/Applications/LibreOffice.app/Contents/Resources/fonts/truetype')]:
        if base.exists():
            for p in sorted(base.rglob('*')):
                if p.is_file() and p.suffix.lower() in ('.ttf','.otf','.ttc'): fonts[str(p)]=sha(p)
    from importlib.metadata import version as package_version
    packages={name:package_version(name) for name in ['Pillow','PyMuPDF','python-pptx','pydantic','jsonschema']}
    result={'agent':{'model':config['agent']['model'],'reasoning_effort':config['agent']['reasoning_effort']},'judge_protocol':'codex_internal_v1','fontconfig_sha256':sha(Path(config['execution']['fontconfig_file'])) if config['execution'].get('fontconfig_file') else None,'packages':packages,'python':sys.version,'os':platform.platform(),'codex':version([config['agent']['executable'],'--version']),
            'libreoffice':version([soffice,'--version']) if soffice else None,'upstream_commit':actual,
            'prompts_hash':tree_hash(ROOT/'prompts'),'implementation_hash':tree_hash(ROOT/'src/pptbench_harness'),
            'fonts':fonts,'official_comparable':False}
    result['fingerprint']=digest(result)
    return result
