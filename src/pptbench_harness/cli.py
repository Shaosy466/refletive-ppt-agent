from __future__ import annotations
import argparse,asyncio,json,shutil
from pathlib import Path
from PIL import Image,ImageDraw
from .config import ROOT,load_config,environment
from .workspace import HarnessError,InputError,ConfigError,atomic_json,read_json
from .checkpoints import Budget
from .models import Probe
from .codex_runner import invoke
from .dataset import task_ids,materialize
from .orchestrator import run_batch
from .reporting import report

async def probe(config):
    import uuid
    w=Path(config['output']['root'])/('probe-'+uuid.uuid4().hex[:8]);w.mkdir(parents=True)
    im=Image.new('RGB',(800,200),'white');ImageDraw.Draw(im).text((30,60),'ORCHID   COBALT   SEVEN',fill='black',font_size=45);im.save(w/'probe.png')
    payload=await invoke(config,Budget(w/'budget.json',config['loop']),w,
        'Read the three labels in the image in order. Use a tool to write probe-ok.txt containing exactly VISUAL_OK in this directory. Return labels and wrote_file. No network or other files.',
        Probe.model_json_schema(),[w/'probe.png'],Probe.model_validate)
    if payload['labels']!=['ORCHID','COBALT','SEVEN'] or not (w/'probe-ok.txt').exists() or (w/'probe-ok.txt').read_text().strip()!='VISUAL_OK':
        raise HarnessError('Visual/tool probe failed')
    atomic_json(w/'result.json',{'passed':True,'payload':payload,'model_identity_verified':False,'requested_model':config['agent']['model'],'effort':config['agent']['reasoning_effort']})
    return str(w)

def parser():
    p=argparse.ArgumentParser(description='Configurable Codex native PPT reconstruction loop')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('doctor','materialize','run','resume','inspect','report','replay'):
        s=sub.add_parser(name);s.add_argument('--config',default=str(ROOT/'configs/default.toml'))
        if name in ('materialize','run','inspect'):
            s.add_argument('--task',action='append');s.add_argument('--task-file',type=Path)
        if name=='doctor':s.add_argument('--agent-probe',action='store_true')
        if name=='materialize':
            s.add_argument('--accept-arxiv-terms',action='store_true');s.add_argument('--resume',action='store_true')
        if name in ('resume','report'):s.add_argument('--run-id',required=True)
        if name=='replay':
            s.add_argument('--from-run',required=True)
            s.add_argument('--recover-compatible',action='store_true',help='Preserve verified stages for runtime-only recovery; renderer must be unchanged')
        if name=='inspect':s.add_argument('--pptx',type=Path,required=True)
        if name in ('run','resume','inspect','replay'):s.add_argument('--require-quality-pass',action='store_true')
    return p

def main(argv=None):
    a=parser().parse_args(argv)
    try:
        c=load_config(a.config)
        if a.command=='doctor':
            e=environment(c);target=Path(c['output']['root'])/'doctor.json';atomic_json(target,e)
            print(json.dumps({'ok':True,'codex':e['codex'],'libreoffice':e['libreoffice'],'environment':str(target)},ensure_ascii=False))
            if a.agent_probe:print('probe:',asyncio.run(probe(c)))
            return 0
        if a.command=='replay':
            from .replay import fork_generation
            from .workspace import inside
            new=fork_generation(inside(Path(c['output']['root']),a.from_run),c,repair_failures=a.recover_compatible)
            _,r=asyncio.run(run_batch(c,[],run_dir=new))
        elif a.command in ('resume','report'):
            run=(Path(c['output']['root'])/a.run_id).resolve()
            if not run.is_relative_to(Path(c['output']['root'])):raise InputError('Invalid run ID')
            if a.command=='report':print(json.dumps(report(run),ensure_ascii=False,indent=2));return 0
            c=read_json(run/'resolved-config.json');_,r=asyncio.run(run_batch(c,[],run_dir=run))
        else:
            ids=list(dict.fromkeys((a.task or [])+(task_ids(a.task_file) if a.task_file else [])))
            if not ids:raise InputError('Provide --task or --task-file')
            if a.command=='materialize':return materialize(c,ids,a.accept_arxiv_terms,a.resume)
            if a.command=='inspect' and len(ids)!=1:raise InputError('Inspect requires exactly one task')
            _,r=asyncio.run(run_batch(c,ids,inspect_pptx=a.pptx.resolve() if a.command=='inspect' else None))
        if any(x['status']=='CONFIG_ERROR' for x in r['tasks']):return 2
        if r['evaluation_incomplete_count']:return 4
        if a.require_quality_pass and not all(x['quality_pass'] for x in r['tasks']):return 5
        return 0
    except ConfigError as exc:print(str(exc));return 2
    except InputError as exc:print(str(exc));return 3
    except (HarnessError,OSError,ValueError) as exc:print(str(exc));return 4
    except KeyboardInterrupt:return 130
if __name__=='__main__':raise SystemExit(main())
