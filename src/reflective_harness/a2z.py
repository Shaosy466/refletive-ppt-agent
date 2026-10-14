from __future__ import annotations
import shutil
from pathlib import Path
from .adapters import CatalogAdapter
from .contracts import Task,Evaluation
from .browser import capture

class A2ZAdapter(CatalogAdapter):
    def __init__(self,root):super().__init__(root,'a2z')
    def doctor(self):
        d=super().doctor()
        available=(self.root/'data/a2z/gdds/small/bin_bit.md').exists()
        d.update(status='partial',ready=available,adapter_implemented=True,
                 blockers=[] if available else ['Download a pinned public GDD into data/a2z/gdds'],
                 evaluation_blockers=['Official source/replay/adaptive scorer unavailable'],
                 protocol='experimental_static_web')
        return d
    def prepare(self,case_id,destination):
        from .artifacts import safe_path
        source=safe_path(self.root/'data/a2z/gdds',case_id+'.md')
        destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
        shutil.copy2(source,destination/'GDD.md')
        return Task(benchmark=self.name,case_id=case_id,revision='74343b5fa8522b4167a355bedbe8c004cb7450e2',
            instruction='Implement the complete game in GDD.md. This development track uses self-contained HTML/JavaScript served offline. '
                        'Use index.html with local assets. Do not load CDN resources. Implement actual interaction, timers, win/loss and reset. '
                        'The GDD is the only task specification; do not look for contracts or reference implementations.',
            public_dir=str(destination),output_contract='index.html and local assets; playable offline browser game',protocol='experimental_static_web')
    async def execute(self,task,workspace,output,candidate_id):return await capture(workspace,output,candidate_id)
    async def evaluate(self,task,submission,output):
        return Evaluation(complete=False,protocol=task.protocol,details={
            'reason':'Official A2Z evaluator release unavailable; no official score fabricated',
            'deviations':['HTML/JS development stack instead of official Phaser/TypeScript/Vite starter',
                          'Fixed public browser smoke is not source/replay/adaptive scoring']})
