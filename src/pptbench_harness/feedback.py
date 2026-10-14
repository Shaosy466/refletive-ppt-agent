import shutil
from pathlib import Path
from .config import ROOT
from .models import Feedback
from .codex_runner import invoke
from .workspace import atomic_json,read_json,ConfigError
from .observer import crop

async def diagnose(candidate,input_dir,config,budget):
    base=candidate/'diagnosis';base.mkdir(exist_ok=True)
    limit=config['loop']['max_explore_per_candidate'];crops=[]
    for iteration in range(limit+1):
        work=base/f'step-{iteration}';work.mkdir(exist_ok=True)
        for src,name in [(input_dir/'reference.png','reference.png'),(candidate/'render/screenshot.png','candidate.png'),
                         (candidate/'consensus.json','findings.json'),(candidate/'raw/object-map.json','object-map.json')]:
            if src.exists() and not (work/name).exists():shutil.copy2(src,work/name)
        atomic_json(work/'source-index.json',{'build.py':(candidate/'source/build.py').read_text()})
        atomic_json(work/'context.json',{'candidate_id':candidate.name,'exploration_allowed':iteration<limit})
        images=[work/'reference.png',work/'candidate.png']
        for p in crops:
            dest=work/p.name
            if not dest.exists():shutil.copy2(p,dest)
            images.append(dest)
        output=await invoke(config,budget,work,(ROOT/'prompts/diagnose.txt').read_text(),Feedback.model_json_schema(),images,Feedback.model_validate)
        feedback=Feedback.model_validate(output)
        if feedback.candidate_id!=candidate.name:raise ConfigError('Feedback candidate mismatch')
        if feedback.action!='explore' or iteration==limit:
            if feedback.action=='explore':feedback.action='revise'
            atomic_json(candidate/'feedback.json',feedback.model_dump());return feedback.model_dump()
        crops=[]
        for n,request in enumerate(feedback.explore_requests):
            p=work/f'crop-{iteration}-{n}.png'
            crop(work/('reference.png' if request.image=='reference' else 'candidate.png'),request,p);crops.append(p)
    raise AssertionError('unreachable')
