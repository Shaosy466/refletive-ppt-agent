import copy
import pytest
from pptbench_harness.upstream_adapter import score_round,consensus,SCORE_SCHEMA
from vlm_judge_harness.issue_ranker import score_enumeration

def empty_enumeration():
    return {'categories':[],'cases':[]}

def test_upstream_schema_is_not_reinvented():
    assert SCORE_SCHEMA['type']=='object'
    assert SCORE_SCHEMA['additionalProperties'] is False

def test_incomplete_never_scored():
    from vlm_judge_harness.issue_ranker import rank_result
    with pytest.raises(ValueError):rank_result({'status':'failed'})

def enumeration(ratio):
    props=SCORE_SCHEMA['properties']['deductions']['properties']
    d={dim:{cat:{'cases':[],'ratio':0} for cat in info['properties']} for dim,info in props.items()}
    target=d['text_and_typography']['improper_typography'];target['ratio']=ratio
    target['cases']=[{'issue_type':'unexpected_wrap','location':'label A','candidate':'two lines','reference':'one line','affected_count':1}]
    return {'deductions':d,'summary_feedback':'Unexpected wrap in label A'}

def test_union_max_and_cli_equivalence(tmp_path):
    import json,subprocess,sys
    results=[]
    for i,ratio in enumerate([.1,.8,.2],1):
        raw,ranked=score_round('task_0004','000',i,{'scoring':{'status':'complete','output':enumeration(ratio)}},'scored')
        results.append(ranked)
        p=tmp_path/f'round-{i}.json';p.write_text(json.dumps(raw))
        subprocess.run([sys.executable,'-m','vlm_judge_harness.issue_ranker',str(p),'--output-dir',str(tmp_path/f'rank-{i}')],check=True,capture_output=True)
        cli=json.loads((tmp_path/f'rank-{i}/results/gpt-6-astra__high/000/task_0004.json').read_text())
        assert cli['ranking']==ranked['ranking']
    merged=consensus(results)
    issues=merged['dimensions']['text_and_typography']['issues']
    assert len(issues)==1
    assert issues[0]['affected_ratio']==.8
    assert merged['total_score']==96.25
