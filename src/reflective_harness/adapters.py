"""Source catalog and explicit capability reporting; registration is not support."""
from pathlib import Path
import json, shutil
from .registry import register, _FACTORIES

CATALOG = {
 'pptbench': ('PPTBench','https://arxiv.org/abs/2609.29718','artifact','existing'),
 'gamedevbench': ('GameDevBench','https://arxiv.org/abs/2602.11103','artifact','Godot 4.4.1; Linux strict worker for official comparison'),
 'scivisagentbench': ('SciVisAgentBench','https://arxiv.org/abs/2603.29139','artifact','Scientific toolchain and task dataset; official evaluation dependencies'),
 '4dcodebench': ('4DCodeBench','https://arxiv.org/abs/2610.03715','artifact','NVIDIA Linux worker, Blender 5.2, dataset and scorer checkpoints'),
 'code4scene': ('Code4Scene','https://arxiv.org/abs/2609.36777','artifact','Unreal 5.8, licensed Fab packs and native scene worker'),
 'a2z': ('A2Z','https://arxiv.org/abs/2609.39564','artifact','Official evaluator release not verified; experimental browser generation only'),
 'ichart2code': ('IChart2Code','https://arxiv.org/abs/2609.32413','artifact','Official repository, task package and evaluator not verified'),
 'edithero': ('EditHero','https://arxiv.org/abs/2610.02298','edit_chain','Dataset chain, Blender 4.2 and blender_kit; regional evaluation implementation'),
 'witness': ('Witness','https://arxiv.org/abs/2609.32208','episode','Public validation engine/API release not verified; website is not the SDK'),
 'longpuzzlebench': ('LongPuzzleBench','https://arxiv.org/abs/2609.34769','episode','Browser runtime and Codex episode adapter'),
}

class CatalogAdapter:
    def __init__(self,root,name):
        self.root=Path(root).resolve();self.name=name
        self.directory,self.paper,self.kind,self.requirement=CATALOG[name]
        self.source=self.root/'vendor'/self.directory
    def doctor(self):
        source_lock=self.source/'.source-lock.json'
        lock=json.loads(source_lock.read_text()) if source_lock.exists() else None
        return {'benchmark':self.name,'kind':self.kind,'paper':self.paper,
                'source_present':(self.source/'README.md').exists(),'source_lock':lock,
                'status':'blocked','ready':False,'blockers':[self.requirement],
                'adapter_implemented':False,'official_comparable':False}
    def prepare(self,*args,**kwargs):
        raise RuntimeError(f'{self.name} is not runnable: '+self.requirement)

class PPTAdapter(CatalogAdapter):
    def __init__(self,root):super().__init__(root,'pptbench')
    def doctor(self):
        d=super().doctor()
        ready=bool(shutil.which('codex')) and (self.source/'src/eval_harness').exists()
        d.update(status='legacy',adapter_implemented=True,ready=ready,blockers=[] if ready else ['Run the PPT bootstrap and doctor'],
                 command='ppt-harness run --task task_0004')
        return d

def register_builtins():
    for name in CATALOG:
        if name not in _FACTORIES:
            register(name,lambda root,n=name:CatalogAdapter(root,n))
    _FACTORIES['pptbench']=PPTAdapter
    # Concrete adapters override catalog entries only when implemented.
    from .longpuzzle import LongPuzzleAdapter
    _FACTORIES['longpuzzlebench']=LongPuzzleAdapter
    from .gamedev import GameDevAdapter
    _FACTORIES['gamedevbench']=GameDevAdapter
    from .a2z import A2ZAdapter
    _FACTORIES['a2z']=A2ZAdapter
    from .scivis import SciVisAdapter
    _FACTORIES['scivisagentbench']=SciVisAdapter
    from .edithero import EditHeroAdapter
    _FACTORIES['edithero']=EditHeroAdapter
