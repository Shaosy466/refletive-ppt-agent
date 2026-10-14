from __future__ import annotations
import asyncio, json, sys, time, importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict
from .adapters import CatalogAdapter
from pptbench_harness.workspace import atomic_json
from pptbench_harness.codex_runner import invoke, usage_from_events
from pptbench_harness.checkpoints import Budget

class GUIResponse(BaseModel):
    model_config=ConfigDict(extra='forbid')
    observation: str
    diagnosis: str
    memory: str
    action_type: Literal['click','double_tap','long_press','drag','swipe','wait','answer']
    x: float | None
    y: float | None
    x2: float | None
    y2: float | None
    duration: float | None
    text: str | None

class LongPuzzleAdapter(CatalogAdapter):
    def __init__(self,root):super().__init__(root,'longpuzzlebench')
    def doctor(self):
        d=super().doctor();blockers=[]
        if not (self.source/'src/mobile_world').is_dir():blockers.append('Missing pinned LongPuzzleBench source')
        if not importlib.util.find_spec('playwright'):blockers.append('Install Playwright')
        if sys.platform=='darwin' and not Path('/Applications/Google Chrome.app').exists():blockers.append('Google Chrome missing; current runtime uses channel=chrome')
        if not (self.source/'games/puzzle_suite/build/web-mobile/index.html').exists():blockers.append('Missing bundled browser build')
        d.update(status='experimental',adapter_implemented=True,ready=not blockers,blockers=blockers)
        return d
    def activate(self):
        p=str(self.source/'src')
        if p not in sys.path:sys.path.insert(0,p)
    def tasks(self):
        self.activate()
        from mobile_world.benchmarks.catalog import load_catalog
        return load_catalog(self.source/'configs/longpuzzlebench.json')
    def run_episode(self,case_id,config,output,max_steps=None):
        self.activate()
        from mobile_world.agents.base import BaseAgent
        from mobile_world.runtime.utils.models import JSONAction
        from mobile_world.benchmarks.evaluator import MiniGameEvaluator
        from mobile_world.benchmarks.mini_games_runner import _execute_episode
        from mobile_world.runtime.web_game_client import WebGameEnvClient
        from mobile_world.runtime.utils.trajectory_logger import TrajLogger
        catalog=self.tasks();task=catalog.get_task(case_id)
        if max_steps is not None:task=task.model_copy(update={'max_steps':max_steps})
        output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
        budget=Budget(output/'budget.json',config['loop'])
        atomic_json(output/'config.json',config)
        atomic_json(output/'task.json',task.model_dump(mode='json'))
        # Only screenshots/public feedback cross the model boundary. The private
        # bridge and scoring config remain in the upstream controller process.
        class CodexGUIAgent(BaseAgent):
            def __init__(self):
                super().__init__();self.memory='';self.step=0
            def predict(self,observation):
                self.step+=1
                work=output/'agent'/f'{self.step:04d}';work.mkdir(parents=True)
                im=work/'screen.png';observation['screenshot'].save(im)
                width,height=observation['screenshot'].size
                public={'goal':self.instruction,'memory':self.memory,'width':width,'height':height,
                        'action_feedback':observation.get('action_feedback')}
                prompt=('You are a visual puzzle player. Observe the screenshot, diagnose what changed after your previous action, '
                    'then choose exactly one GUI action. All game knowledge MUST come from screenshots and public action feedback. '
                    'Do not inspect source code, DOM, browser state, files outside this directory or network. '
                    'Coordinates are screenshot pixels, not normalized. x/y are start and x2/y2 are end for drags. '
                    'Use null for unused fields. Duration is in seconds. Use answer only if the screenshot visibly shows completion. '
                    'Keep concise persistent memory of observed moves, hypotheses, failed plans and next strategy. '
                    'No score or hidden state is provided.\n'+json.dumps(public,ensure_ascii=False))
                began=time.monotonic()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    raw=executor.submit(lambda: asyncio.run(invoke(config,budget,work,prompt,GUIResponse.model_json_schema(),[im]))).result()
                self._total_model_latency_seconds+=time.monotonic()-began
                self._total_model_calls+=1
                r=GUIResponse.model_validate(raw);self.memory=r.memory
                for value,limit in ((r.x,width),(r.x2,width),(r.y,height),(r.y2,height)):
                    if value is not None and not 0<=value<limit:raise ValueError('GUI coordinate outside screenshot')
                if r.duration is not None and not 0<=r.duration<=10:raise ValueError('GUI duration out of range')
                payload={k:v for k,v in r.model_dump().items() if k not in ('observation','diagnosis','memory') and v is not None}
                if r.action_type in ('drag','swipe'):
                    payload.update(start_x=round(r.x),start_y=round(r.y),end_x=round(r.x2),end_y=round(r.y2))
                payload.pop('x2',None);payload.pop('y2',None)
                duration=payload.pop('duration',None)
                if duration is not None:payload['action_json']={'duration':duration}
                action=JSONAction.model_validate(payload)
                atomic_json(work/'public-input.json',public)
                atomic_json(work/'decision.json',r.model_dump())
                for events in (work/'.harness').glob('attempt-*/events.jsonl'):
                    u=usage_from_events(events) or {}
                    self._total_prompt_tokens+=u.get('input_tokens',0)
                    self._total_completion_tokens+=u.get('output_tokens',0)
                    self._total_cached_tokens+=u.get('cached_input_tokens',0)
                return json.dumps(raw),action
        evaluator=MiniGameEvaluator()
        env=WebGameEnvClient(project_path=self.source/'games/puzzle_suite',build_dir='build/web-mobile',
            build_on_start=False,task_catalog=catalog,evaluator=evaluator,headless=True,
            browser_launch_options={'channel':'chrome'})
        agent=CodexGUIAgent()
        try:
            env.start()
            result=_execute_episode(env=env,evaluator=evaluator,task=task,agent=agent,
                traj_logger=TrajLogger(str(output/'trajectories'),task.task_id),
                agent_information={'model_name':config['agent']['model'],'reasoning_effort':config['agent']['reasoning_effort'],
                                   'agent_framework':'reflective_harness_codex','protocol':'controlled_single_level_development'},
                run_index=1,wall_clock_timeout_slack_seconds=config['loop']['task_timeout_seconds'])
            raw=result.model_dump(mode='json')
            atomic_json(output/'upstream-result.json',raw)
            report={'benchmark':self.name,'case_id':case_id,'status':'error' if raw.get('termination_reason') in ('agent_error','environment_error') else 'complete',
                    'task_success':raw['task_success'],'game_score':raw['game_score'],'termination_reason':raw.get('termination_reason'),'errors':raw.get('errors',[]),
                    'official_comparable':False,'protocol':'controlled_single_level_development',
                    'agent_calls':budget.calls,'source_lock':self.doctor()['source_lock'],
                    'limitations':['Single catalog level, not full autonomous cell','Local development filesystem is not strict solver isolation']}
            atomic_json(output/'result.json',report)
            return report
        except BaseException as exc:
            atomic_json(output/'error.json',{'type':type(exc).__name__,'message':str(exc)})
            raise
        finally:
            env.close();budget.save()
