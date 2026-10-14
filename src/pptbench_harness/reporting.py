from pathlib import Path
from statistics import mean
from .workspace import read_json,atomic_json

def report(run):
    manifest=read_json(run/'manifest.json');results=[]
    env=read_json(run/'environment.json') if (run/'environment.json').exists() else {}
    for t in manifest['tasks']:
        p=run/'tasks'/t/'final/result.json'
        if p.exists():results.append(read_json(p))
    complete=[r for r in results if r['evaluation_complete']]
    passed=[r for r in complete if r['internal_gate_pass']]
    all_complete=len(complete)==len(manifest['tasks'])
    r={'run_id':run.name,'planned_tasks':len(manifest['tasks']),'executed_tasks':len(results),
       'evaluation_complete_count':len(complete),'evaluation_incomplete_count':len(manifest['tasks'])-len(complete),
       'artifact_failures':sum(not x['artifact_valid'] for x in complete),
       'internal_gate_pass_rate':len(passed)/len(manifest['tasks']) if all_complete else None,
       'mean_score':mean(x['internal_score'] for x in complete) if all_complete else None,
       'completed_subset_mean':mean(x['internal_score'] for x in complete) if complete else None,
       'passed_mean_score':mean(x['internal_score'] for x in passed) if passed else None,
       'agent_calls':sum(x['agent_calls'] for x in results),'elapsed_seconds':sum(x['elapsed_seconds'] for x in results),
       'cost_usd':None,'judge_protocol':env.get('judge_protocol','astra_internal_v1'),'agent':env.get('agent'),'official_comparable':False,'tasks':results}
    atomic_json(run/'report.json',r)
    lines=['# Harness run '+run.name,'','Codex internal evaluation; not official PPTBench scores. See report.json for model/effort.','',
           f"Coverage: {len(complete)}/{len(manifest['tasks'])} complete. Mean score: {r['mean_score']}. Agent calls: {r['agent_calls']}.",'']
    for x in results:lines.append(f"- {x['task_id']}: {x['status']}; score={x['internal_score']}; candidate={x['selected_candidate']}; reason={x['stop_reason']}")
    (run/'report.md').write_text('\n'.join(lines)+'\n')
    return r
