from __future__ import annotations
import asyncio,sys,shutil
from pathlib import Path
from .codex_runner import process
from .workspace import atomic_json,read_json,sha,HarnessError,snapshot_hashes
from .checkpoints import restore,commit
from .runtime import slot

async def execute_build(source,out,config,budget):
    cached=restore(out/'build.complete.json')
    if cached is not None:return cached
    out.mkdir(parents=True,exist_ok=True);budget.check()
    argv=[sys.executable,str(source/'build.py'),'--output',str(out/'reconstruction.pptx'),'--object-map',str(out/'object-map.json')]
    try:rc=await process(argv,source,out/'stdout.log',out/'stderr.log',min(config['execution']['build_timeout_seconds'],budget.remaining))
    except asyncio.TimeoutError:rc=-1
    finally:budget.save()
    payload={'exit_code':rc,'valid_output':rc==0 and (out/'reconstruction.pptx').is_file() and (out/'object-map.json').is_file()}
    files=[out/'stdout.log',out/'stderr.log']
    files += [p for p in [out/'reconstruction.pptx',out/'object-map.json'] if p.exists()]
    commit(out/'build.complete.json',payload,files)
    return payload

async def validate_and_render(candidate,task_input,config,budget):
    done=restore(candidate/'artifact.complete.json')
    if done is not None:return done
    raw=candidate/'raw/reconstruction.pptx';validated=candidate/'validated/reconstruction.pptx'
    validated.parent.mkdir(exist_ok=True);shutil.copy2(raw,validated)
    job={'pptx':str(validated),'reference':str(task_input/'reference.png'),
         'assets':[str(p) for p in sorted((task_input/'assets').rglob('*')) if p.is_file()],
         'soffice':config['execution']['soffice'],'screenshot':str(candidate/'render/screenshot.png'),
         'report':str(candidate/'artifact-report.json'),'object_map':str(candidate/'raw/object-map.json'),
         'require_map':(candidate/'source/build.py').exists()}
    atomic_json(candidate/'artifact-job.json',job)
    for attempt in range(2):
        budget.check()
        try:
            async with slot('render'):
                budget.check()
                rc=await process([sys.executable,'-m','pptbench_harness.validator',str(candidate/'artifact-job.json')],candidate,
                    candidate/f'validation-{attempt}.stdout',candidate/f'validation-{attempt}.stderr',min(config['execution']['render_timeout_seconds'],budget.remaining),
                    extra_env={'FONTCONFIG_FILE':config['execution']['fontconfig_file']} if config['execution'].get('fontconfig_file') else None)
        except asyncio.TimeoutError:rc=124
        finally:budget.save()
        if rc==0 or rc==3:break
    if rc not in (0,3): raise HarnessError(f'Validation/render infrastructure failed: {candidate}')
    report=read_json(candidate/'artifact-report.json')
    if report.get('infra_error'): raise HarnessError(report['infra_error'])
    files=[candidate/'artifact-report.json',validated,raw]
    if report['valid']:files += [candidate/'render/screenshot.png']
    report['raw_pptx_sha256']=sha(raw);report['validated_pptx_sha256']=sha(validated)
    report['normalization_changed_bytes']=sha(raw)!=sha(validated)
    commit(candidate/'artifact.complete.json',report,files)
    return report
