"""EditHero local development chain: original source + conditioning views only.

Uses VTK previews, not the official Blender rig. Mesh delivery checks are not
EditHero's regional geometry/appearance quality metrics.
"""
from __future__ import annotations
import asyncio,json,shutil,sys,importlib.util
from pathlib import Path
from .adapters import CatalogAdapter
from .contracts import Task,Execution,Evaluation,Metric
from .artifacts import evidence
from pptbench_harness.codex_runner import process

class EditHeroAdapter(CatalogAdapter):
    def __init__(self,root):super().__init__(root,'edithero');self.data=self.root/'data/edithero'
    def doctor(self):
        d=super().doctor();missing=[]
        for module in ['vtk','trimesh']:
            if not importlib.util.find_spec(module):missing.append('Install '+module)
        if not (self.data/'sample/data/states/A/1a3267df_s0/turn00.glb').is_file():missing.append('Download original sample mesh')
        if not (self.data/'sample/chain.json').is_file():missing.append('Download sample chain instructions')
        for i in range(1,6):
            if not (self.data/f'sample/data/renders/A/1a3267df_s0/turn{i:02d}/view0_cond.png').exists():missing.append(f'Missing conditioning image turn {i}')
        d.update(ready=not missing,status='partial',blockers=missing,adapter_implemented=True,
            protocol='local_vtk_chain_delivery',evaluation_blockers=['Official regional metrics and Blender rig not integrated'])
        return d
    def prepare(self,case_id,destination):
        if case_id!='A/1a3267df_s0':raise ValueError('Only the released sample chain is prepared')
        destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
        chain=json.loads((self.data/'sample/chain.json').read_text())
        shutil.copy2(self.data/'sample/data/states/A/1a3267df_s0/turn00.glb',destination/'source.glb')
        for i in range(1,6):shutil.copy2(self.data/f'sample/data/renders/A/1a3267df_s0/turn{i:02d}/view0_cond.png',destination/f'target-{i:02d}.png')
        (destination/'instructions.json').write_text(json.dumps(chain,indent=2))
        return Task(benchmark=self.name,case_id=case_id,revision='dba807e8c98f995bc0fad144da38b574d4539fb5',kind='edit_chain',
            instruction='Edit source.glb through the five sequential instructions in instructions.json. Each turn edits YOUR previous output. '
            'Target-NN.png is that turn\'s allowed conditioning view. Preserve unrelated geometry/materials. '
            'Use Python trimesh to create/edit parts procedurally. No downloaded assets, generative models or target meshes. '
            'Write build.py that writes turn01.glb through turn05.glb, each a full usable mesh with materials. '
            'Preserve the original coordinate system. Keep part identities where possible. Inspect source mesh and images before editing.',
            public_dir=str(destination),output_contract='build.py; turn01.glb .. turn05.glb, self-rollout sequential editing',protocol='local_vtk_chain_delivery')
    async def execute(self,task,workspace,output,candidate_id):
        try:rc=await process([sys.executable,'build.py'],workspace,output/'build.stdout.log',output/'build.stderr.log',180)
        except asyncio.TimeoutError:rc=124
        if rc==0:
            script=Path(__file__).with_name('mesh_preview.py')
            try:render=await process([sys.executable,str(script),str(workspace),str(output)],workspace,output/'render.stdout.log',output/'render.stderr.log',180)
            except asyncio.TimeoutError:render=124
        else:render=-1
        items=[evidence(p,output,'log',candidate_id) for p in output.glob('*.log')]
        items.extend(evidence(p,output,'image',candidate_id) for p in sorted(output.glob('*.png')))
        return Execution(ok=rc==0 and render==0,evidence=items,public_feedback={'build_exit':rc,'render_exit':render,'preview':'VTK canonical view; not official Blender camera'})
    async def evaluate(self,task,submission,output):
        import trimesh
        checks=[]
        for i in range(1,6):
            p=submission/f'turn{i:02d}.glb'
            try:
                s=trimesh.load(p,force='scene');faces=sum(len(m.faces) for m in s.geometry.values())
                checks.append({'turn':i,'delivered':faces>0,'faces':faces})
            except Exception as exc:checks.append({'turn':i,'delivered':False,'error':str(exc)})
        return Evaluation(complete=False,protocol=task.protocol,
            metrics={'delivered_turns':Metric(value=sum(c['delivered'] for c in checks),unit='count out of 5',direction='higher',status='ok')},
            details={'turns':checks,'reason':'Delivery validation only; official edited-region/preservation/appearance metrics unavailable'})
