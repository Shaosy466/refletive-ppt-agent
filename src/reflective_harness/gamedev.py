from __future__ import annotations
import asyncio,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
from .adapters import CatalogAdapter
from .contracts import Task,Execution,Evaluation,Metric
from .artifacts import safe_path,evidence
from pptbench_harness.codex_runner import process

class GameDevAdapter(CatalogAdapter):
    def __init__(self,root):
        super().__init__(root,'gamedevbench')
        local=self.root/'.cache/tools/Godot.app/Contents/MacOS/Godot'
        self.godot=os.environ.get('GODOT_EXEC_PATH') or shutil.which('godot') or str(local)
    def doctor(self):
        d=super().doctor();block=[]
        if not Path(self.godot).is_file():block.append('Godot 4.4.1 executable missing; set GODOT_EXEC_PATH')
        else:
            try:
                v=subprocess.run([self.godot,'--version'],capture_output=True,text=True,timeout=15).stdout.strip()
                d['godot_version']=v
                if not v.startswith('4.4.1.'):block.append('Exact Godot 4.4.1 required')
            except (OSError,subprocess.TimeoutExpired) as exc:block.append(str(exc))
        if not (self.source/'tasks/task_0002.zip').exists():block.append('Task archive missing')
        d.update(ready=not block,blockers=block,status='experimental',adapter_implemented=True)
        return d
    def prepare(self,case_id,destination):
        import re
        if not re.fullmatch(r'task_\d{4}',case_id):raise ValueError('Invalid GameDevBench task ID')
        archive=self.source/'tasks'/f'{case_id}.zip'
        destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
        hidden={'test.gd','test.gd.uid','test.tscn','task_config.json','task_validation.md','validation.md'}
        with zipfile.ZipFile(archive) as z:
            cfg=json.loads(z.read(f'tasks/{case_id}/task_config.json'))
            prefix=f'tasks/{case_id}/'
            for info in z.infolist():
                if not info.filename.startswith(prefix):raise ValueError('Unexpected task archive layout')
                relative=info.filename[len(prefix):]
                if not relative or info.is_dir():continue
                parts=Path(relative).parts
                if '.godot' in parts or Path(relative).name in hidden:continue
                if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlink in task archive')
                target=safe_path(destination,relative);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
        return Task(benchmark=self.name,case_id=case_id,revision=self.doctor()['source_lock']['commit'],
            instruction=cfg['instruction'],public_dir=str(destination),output_contract='Editable native Godot project. Preserve existing project and assets. Godot 4.4.1.')
    async def _cmd(self,args,work,out,name,timeout=90):
        try:return await process([self.godot,*args],work,out/f'{name}.stdout.log',out/f'{name}.stderr.log',timeout)
        except asyncio.TimeoutError:return 124
    async def execute(self,task,workspace,output,candidate_id):
        rc=await self._cmd(['--headless','--import','--quit','--path',str(workspace)],workspace,output,'import')
        # PNG movie output captures the actual rendering, independent of author claims.
        render=await self._cmd(['--path',str(workspace),'--resolution','640x480','--fixed-fps','10',
            '--write-movie',str(output/'frame.png'),'--quit-after','10'],workspace,output,'render',120) if rc==0 else -1
        files=[evidence(p,output,'log',candidate_id) for p in output.glob('*.log')]
        images=sorted(output.glob('*.png'))
        # Supply a bounded, reproducible sample, retain the complete rendered sequence.
        for p in images[::max(1,len(images)//3)][:3]:files.append(evidence(p,output,'image',candidate_id))
        return Execution(ok=rc==0 and render==0 and bool(images),evidence=files,
            public_feedback={'import_exit_code':rc,'render_exit_code':render,'frames':len(images)})
    async def evaluate(self,task,submission,output):
        work=output/'project';shutil.copytree(submission,work)
        # Overlay original immutable tests after solver freeze. Never trust tests
        # supplied or modified by the solver.
        with zipfile.ZipFile(self.source/'tasks'/f'{task.case_id}.zip') as z:
            for relative in ('scripts/test.gd','scripts/test.gd.uid','scenes/test.tscn'):
                name=f'tasks/{task.case_id}/{relative}'
                if name in z.namelist():
                    target=safe_path(work,relative);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
        rc=await self._cmd(['--headless','--import','--quit','--path',str(work)],work,output,'import')
        code=await self._cmd(['--headless','--path',str(work),'scenes/test.tscn'],work,output,'test') if rc==0 else rc
        sys.path.insert(0,str(self.source)) if str(self.source) not in sys.path else None
        from gamedevbench.src.utils.validation import ValidationParser
        text='\n'.join(p.read_text(errors='replace') for p in output.glob('test.*.log'))
        parsed=ValidationParser.parse_output(text)
        completed=code==0 and ('VALIDATION_PASSED' in text or 'VALIDATION_FAILED' in text)
        return Evaluation(complete=completed,protocol='upstream_tests_local_development',
            metrics={'pass':Metric(value=float(parsed.success) if completed else None,unit='binary',direction='higher',status='ok' if completed else 'error')},
            details={'exit_code':code,'validation':parsed.to_dict(),'platform':sys.platform,'strict_confinement':False})
