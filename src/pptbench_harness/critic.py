import shutil
from pathlib import Path
from .codex_runner import invoke
from .workspace import atomic_json
from .checkpoints import restore,commit
from .observer import compare
from .upstream_adapter import GATE_SCHEMA,SCORE_SCHEMA,validate_gate,validate_score,with_tool_inspection_guidance,score_round,consensus

async def judge_candidate(candidate,task_id,input_dir,config,budget):
    cached=restore(candidate/'judge.complete.json')
    if cached is not None:return cached
    evidence=candidate/'evidence';evidence.mkdir(exist_ok=True)
    compare(input_dir/'reference.png',candidate/'render/screenshot.png',evidence/'comparison.png')
    up=Path(config['dataset']['upstream_root']);rounds=[]
    for index in range(1,4):
        rd=candidate/'judge'/f'round-{index}';rd.mkdir(parents=True,exist_ok=True)
        ranked=restore(rd/'complete.json')
        if ranked is None:
            stages={};final='scored'
            for stage,filename in [('semantic_gate','semantic_gate.txt'),('render_gate','render_gate.txt'),('scoring','detail_findings.txt')]:
                work=rd/stage;work.mkdir(exist_ok=True)
                for src,name in [(input_dir/'reference.png','reference.png'),(candidate/'render/screenshot.png','candidate.png'),
                                 (evidence/'comparison.png','comparison.png'),(evidence/'comparison.json','comparison-metadata.json')]:
                    if not (work/name).exists():shutil.copy2(src,work/name)
                prompt=with_tool_inspection_guidance((up/'configs/vlm_judge'/filename).read_text())
                images=[work/n for n in ('comparison.png','reference.png','candidate.png')]
                output=await invoke(config,budget,work,prompt,SCORE_SCHEMA if stage=='scoring' else GATE_SCHEMA,images,
                                    validate_score if stage=='scoring' else validate_gate)
                stages[stage]={'status':'complete','output':output}
                if stage!='scoring' and output['gate_keeper']['triggered']:
                    final=stage;break
            raw,ranked=score_round(task_id,candidate.name,index,stages,final,config['agent']['model'],config['agent']['reasoning_effort'])
            atomic_json(rd/'raw.json',raw);atomic_json(rd/'ranked.json',ranked)
            commit(rd/'complete.json',ranked,[rd/'raw.json',rd/'ranked.json'])
        rounds.append(ranked)
    merged=consensus(rounds);atomic_json(candidate/'consensus.json',merged)
    commit(candidate/'judge.complete.json',merged,[candidate/'consensus.json',*[candidate/'judge'/f'round-{n}'/'ranked.json' for n in range(1,4)]])
    return merged
