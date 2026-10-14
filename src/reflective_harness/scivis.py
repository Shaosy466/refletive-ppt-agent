from __future__ import annotations
import importlib.util,json,sys,shutil
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field
from .adapters import CatalogAdapter
from .contracts import Task,Execution,Evaluation,Metric
from .artifacts import evidence
from .config import load_config
from pptbench_harness.codex_runner import process,invoke
from pptbench_harness.checkpoints import Budget

class RubricResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scores: list[float]
    reasons: list[str]

class SciVisAdapter(CatalogAdapter):
    def __init__(self,root):super().__init__(root,'scivisagentbench');self.config=None
    def doctor(self):
        d=super().doctor();missing=[]
        if not importlib.util.find_spec('vtk'):missing.append('Install vtk for local shrink-sphere profile')
        if not (self.source/'benchmark/eval_cases/paraview/paraview_cases.yaml').exists():missing.append('Pinned task definitions missing')
        d.update(status='partial',ready=not missing,blockers=missing,adapter_implemented=True,
                 supported_cases=['shrink-sphere'],protocol='codex_rubric_local_vtk')
        return d
    def _row(self):
        import yaml
        rows=yaml.safe_load((self.source/'benchmark/eval_cases/paraview/paraview_cases.yaml').read_text())
        return next(r for r in rows if 'shrink-sphere/results/' in r.get('vars',{}).get('question',''))
    def prepare(self,case_id,destination):
        if case_id!='shrink-sphere':raise ValueError('Only shrink-sphere profile implemented; other SciVis suites are blocked')
        destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
        instruction=self._row()['vars']['question'].replace('{agent_mode}','reflective')
        (destination/'TASK.txt').write_text(instruction)
        return Task(benchmark=self.name,case_id=case_id,revision=self.doctor()['source_lock']['commit'],instruction=instruction+
            '\nUse installed Python vtk for this local development profile. Write build.py as the executable entrypoint; '
            'use offscreen rendering. Save the requested PNG plus your script. The controller runs build.py.',
            public_dir=str(destination),output_contract='build.py and shrink-sphere/results/reflective/shrink-sphere.png',protocol='codex_rubric_local_vtk')
    async def execute(self,task,workspace,output,candidate_id):
        import asyncio
        from PIL import Image
        try:rc=await process([sys.executable,'build.py'],workspace,output/'stdout.log',output/'stderr.log',180)
        except asyncio.TimeoutError:rc=124
        image=workspace/'shrink-sphere/results/reflective/shrink-sphere.png'
        items=[evidence(output/n,output,'log',candidate_id) for n in ('stdout.log','stderr.log')];size=None
        if image.is_file():
            with Image.open(image) as im:size=im.size
            shutil.copy2(image,output/'result.png');items.append(evidence(output/'result.png',output,'image',candidate_id))
        return Execution(ok=rc==0 and size==(1920,1080),evidence=items,public_feedback={'exit_code':rc,'image_size':size})
    async def evaluate(self,task,submission,output):
        image=submission/'shrink-sphere/results/reflective/shrink-sphere.png'
        if not image.is_file():return Evaluation(complete=False,protocol=task.protocol,details={'error':'No PNG submission'})
        from PIL import Image
        with Image.open(image) as im:im.verify()
        work=output/'judge';work.mkdir();shutil.copy2(image,work/'result.png')
        rubric=self._row()['assert'][0]['value']
        config=self.config or load_config();budget=Budget(output/'budget.json',{'max_agent_calls':2,'task_timeout_seconds':1200})
        raw=await invoke(config,budget,work,
            'Evaluate the frozen visualization image using the four criteria below. Return exactly four scores 0 to 10 and four reasons, in criterion order. '
            'Use only the image and criteria. Do not read outside this directory. This is a local Codex judge variant, not official reproduction.\n'+rubric,
            RubricResult.model_json_schema(),[work/'result.png'])
        if len(raw['scores'])!=4 or len(raw['reasons'])!=4 or any(not 0<=s<=10 for s in raw['scores']):raise ValueError('Invalid rubric result')
        return Evaluation(complete=True,protocol=task.protocol,metrics={
            'rubric_mean':Metric(value=sum(raw['scores'])/4,unit='0-10',direction='higher',status='ok')},
            details={'rubric':raw,'judge_model':config['agent']['model'],'effort':config['agent']['reasoning_effort'],
                     'official_suite_aggregation':False,'reference_metrics_computed':False,'judge_calls':budget.calls})
