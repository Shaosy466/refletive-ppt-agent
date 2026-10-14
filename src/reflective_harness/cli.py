from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
from .registry import discover,get
from .config import load_config, ROOT
from pptbench_harness.workspace import atomic_json

def main(argv=None):
    p=argparse.ArgumentParser(description='Multimodal benchmark adapters; readiness is reported explicitly')
    p.add_argument('--root',type=Path,default=ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    r=sub.add_parser('resume');r.add_argument('--run',type=Path,required=True)
    for command in ['doctor','tasks','run']:
        s=sub.add_parser(command);s.add_argument('--benchmark',required=True)
        if command=='run':
            s.add_argument('--task',required=True);s.add_argument('--config',default=None)
            s.add_argument('--output',type=Path);s.add_argument('--max-steps',type=int)
    args=p.parse_args(argv)
    try:
        if args.command=='resume':
            import asyncio
            from .contracts import Task
            from .controller import run_artifact
            run=args.run.resolve()
            state=json.loads((run/'run.json').read_text())
            task=Task.model_validate(state['task'])
            config=json.loads((run/'config.json').read_text())
            adapter=get(task.benchmark,args.root);adapter.config=config
            result=asyncio.run(run_artifact(adapter,task,config,run))
        elif args.command=='list':
            result=[get(n,args.root).doctor() for n in discover()]
        else:
            adapter=get(args.benchmark,args.root)
            if args.command=='doctor':result=adapter.doctor()
            elif args.command=='tasks':
                if not hasattr(adapter,'tasks'):raise RuntimeError('Task loading is not implemented for this adapter')
                result=[{'id':t.task_id,'game':t.game_id,'difficulty':t.difficulty} for t in adapter.tasks().tasks]
            else:
                status=adapter.doctor()
                if not status['ready']:raise RuntimeError('; '.join(status['blockers']))
                config=load_config(args.config)
                adapter.config=config
                out=args.output or args.root/'runs'/('multi-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+args.benchmark)
                if hasattr(adapter,'run_episode'):result=adapter.run_episode(args.task,config,out,args.max_steps)
                elif args.benchmark=='pptbench':
                    from pptbench_harness.cli import main as ppt_main
                    return ppt_main(['run','--task',args.task]+(['--config',args.config] if args.config else []))
                else:
                    import asyncio
                    from .controller import run_artifact
                    public=out.parent/(out.name+'-public')
                    task=adapter.prepare(args.task,public)
                    result=asyncio.run(run_artifact(adapter,task,config,out))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if isinstance(result,dict) and (result.get('ready') is False or result.get('status')=='error'):return 4
        return 0
    except (OSError,ValueError,RuntimeError,ImportError) as exc:
        print(json.dumps({'status':'error','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 4
if __name__=='__main__':raise SystemExit(main())
