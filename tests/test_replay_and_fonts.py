import os,subprocess
from pathlib import Path
import pytest
from pptbench_harness.config import load_config
from pptbench_harness.workspace import atomic_json,read_json,sha
from pptbench_harness.checkpoints import commit,restore
from pptbench_harness.replay import fork_generation
from pptbench_harness.native import NativeSlide

def test_replay_preserves_generation_not_scores(tmp_path,monkeypatch):
    c=load_config();c['output']['root']=str(tmp_path/'runs')
    old=tmp_path/'old';task=old/'tasks/task_0001';source=task/'candidates/000/source';source.mkdir(parents=True)
    build=source/'build.py';build.write_text('print("frozen source")')
    atomic_json(old/'manifest.json',{'tasks':['task_0001'],'inspect_pptx':None})
    atomic_json(old/'resolved-config.json',c)
    atomic_json(task/'budget.json',{'calls':5,'elapsed_seconds':30,'reserved_seconds':0})
    commit(task/'candidates/000/author.complete.json',{'entrypoint':'build.py'},[build])
    atomic_json(task/'candidates/000/consensus.json',{'total_score':99})
    monkeypatch.setattr('pptbench_harness.replay.environment',lambda config:{'fingerprint':'test'})
    new=fork_generation(old,c)
    newbuild=new/'tasks/task_0001/candidates/000/source/build.py'
    assert sha(newbuild)==sha(build)
    assert not (newbuild.parent.parent/'consensus.json').exists()
    assert restore(newbuild.parent.parent/'author.complete.json')['entrypoint']=='build.py'
    assert read_json(new/'tasks/task_0001/budget.json')['calls']==5
    assert read_json(new/'tasks/task_0001/budget.json')['usage_complete'] is False
    assert (old/'tasks/task_0001/candidates/000/consensus.json').exists()

def test_macos_fontconfig_uses_requested_font(tmp_path):
    import fitz
    c=load_config();fc=c['execution'].get('fontconfig_file')
    if not fc:pytest.skip('macOS font regression')
    s=NativeSlide();sh=s.text('label',[.1,.2,.7,.2],'Comic Sans font probe',24)
    for r in sh.text_frame.paragraphs[0].runs:r.font.name='Comic Sans MS'
    p=tmp_path/'font.pptx';s.save(p,tmp_path/'map.json')
    subprocess.run([c['execution']['soffice'],f'-env:UserInstallation={(tmp_path/"profile").as_uri()}',
        '--headless','--convert-to','pdf','--outdir',str(tmp_path),str(p)],
        env={**os.environ,'FONTCONFIG_FILE':fc,'XDG_CACHE_HOME':str(tmp_path/'cache')},check=True,capture_output=True,timeout=120)
    doc=fitz.open(tmp_path/'font.pdf');fonts=doc[0].get_fonts()
    assert any('ComicSans' in f[3] for f in fonts),fonts

def test_compatible_recovery_rejects_font_change(tmp_path,monkeypatch):
    from pptbench_harness.workspace import ConfigError
    c=load_config();c['output']['root']=str(tmp_path/'runs')
    old=tmp_path/'old';atomic_json(old/'manifest.json',{'tasks':[]})
    atomic_json(old/'resolved-config.json',c)
    atomic_json(old/'environment.json',{'fontconfig_sha256':'old'})
    monkeypatch.setattr('pptbench_harness.replay.environment',lambda config:{'fontconfig_sha256':'new'})
    with pytest.raises(ConfigError,match='fontconfig'):fork_generation(old,c,repair_failures=True)
