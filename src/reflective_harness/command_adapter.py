"""Extension point for trusted, operator-authored runtime/evaluator command specs.

Commands are argv arrays (never shell strings). This adapter is development-only;
worker/container isolation is the operator's responsibility. Do not load specs
from untrusted benchmark submissions.
"""
import asyncio,json,shutil
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field
from .contracts import Task,Execution,Evaluation
from .artifacts import safe_path,evidence
from pptbench_harness.codex_runner import process

class CommandSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    task: Task
    execute: list[str] = Field(min_length=1)
    evaluate: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=180,gt=0,le=7200)
    evidence_files: dict[str,str] = Field(default_factory=dict)

class CommandAdapter:
    def __init__(self,spec: CommandSpec):self.spec=spec;self.name=spec.task.benchmark
    def doctor(self):return {'ready':True,'status':'experimental','official_comparable':False}
    @staticmethod
    def argv(template,workspace,output):
        # Only two exact tokens are expanded. Braces in Python/JS remain literal.
        return [s.replace('{workspace}',str(workspace)).replace('{output}',str(output)) for s in template]
    async def execute(self,task,workspace,output,candidate_id):
        try:
            rc=await process(self.argv(self.spec.execute,workspace,output),workspace,output/'stdout.log',output/'stderr.log',self.spec.timeout_seconds)
        except asyncio.TimeoutError:
            rc=124
        items=[evidence(output/name,output,'log',candidate_id) for name in ('stdout.log','stderr.log')]
        missing=[]
        for relative,kind in self.spec.evidence_files.items():
            source=safe_path(workspace,relative)
            if not source.is_file():missing.append(relative);continue
            dest=safe_path(output,relative);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            items.append(evidence(dest,output,kind,candidate_id))
        return Execution(ok=rc==0 and not missing,evidence=items,public_feedback={'exit_code':rc,'missing_evidence':missing})
    async def evaluate(self,task,submission,output):
        try:
            rc=await process(self.argv(self.spec.evaluate,submission,output),output,output/'stdout.log',output/'stderr.log',self.spec.timeout_seconds)
        except asyncio.TimeoutError:rc=124
        result=output/'evaluation.json'
        if rc or not result.is_file():
            return Evaluation(complete=False,protocol=task.protocol,details={'exit_code':rc,'error':'Evaluator did not complete'})
        parsed=Evaluation.model_validate_json(result.read_text())
        parsed.official_comparable=False
        return parsed
