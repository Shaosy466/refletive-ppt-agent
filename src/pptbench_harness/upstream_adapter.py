"""All coupling to frozen upstream private symbols is confined to this module."""
from vlm_judge_harness.judge import GATE_SCHEMA,SCORE_SCHEMA,validate_gate,validate_score,make_blind_composite,with_tool_inspection_guidance
from vlm_judge_harness.issue_ranker import rank_result
from vlm_judge_harness.consensus_ranker import merge_ranked_results

def score_round(task_id,candidate_id,round_id,stages,final_status,model='gpt-6-astra',effort='high'):
    raw={'schema':'pptbench-judge-result','protocol_id':'codex_internal_v1','status':'complete',
         'task_id':task_id,'candidate_id':candidate_id,'judge_model':model,'judge_effort':effort,
         'final_status':final_status,'stages':stages}
    ranked=rank_result(raw);ranked['round_id']=str(round_id);ranked['judge_round']=str(round_id)
    return raw,ranked

def consensus(rounds):
    if len({r['round_id'] for r in rounds})!=3: raise ValueError('Three distinct rounds required')
    return merge_ranked_results(rounds,expected_rounds=3)
