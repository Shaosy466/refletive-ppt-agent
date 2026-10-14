import json
from pathlib import Path
import pytest
from reflective_harness.contracts import strict_schema,Review
from reflective_harness.gamedev import GameDevAdapter
from reflective_harness.config import load_config
from reflective_harness.artifacts import manifest

def test_review_schema_all_properties_required():
    schema=strict_schema(Review)
    def check(x):
        if isinstance(x,dict):
            if x.get('type')=='object':
                assert set(x['required'])==set(x['properties'])
                assert x['additionalProperties'] is False
            for value in x.values():check(value)
        elif isinstance(x,list):
            for value in x:check(value)
    check(schema)

def test_gamedev_public_view_does_not_copy_tests(tmp_path):
    import zipfile
    source=tmp_path/'vendor/GameDevBench';(source/'tasks').mkdir(parents=True)
    (source/'.source-lock.json').write_text(json.dumps({'commit':'test'}))
    with zipfile.ZipFile(source/'tasks/task_0002.zip','w') as z:
        for n,value in {'task_config.json':json.dumps({'instruction':'public requirement'}),'scripts/test.gd':'SECRET','scenes/test.tscn':'SECRET','validation.md':'SECRET','task_validation.md':'SECRET','scripts/main.gd':'public source','project.godot':'public project'}.items():
            z.writestr('tasks/task_0002/'+n,value)
    adapter=GameDevAdapter(tmp_path);public=tmp_path/'public'
    task=adapter.prepare('task_0002',public)
    assert task.instruction=='public requirement'
    assert set(manifest(public))=={'scripts/main.gd','project.godot'}

def test_no_ppt_specific_configuration_required():
    root=Path(__file__).resolve().parents[1]
    c=load_config(root/'configs/multimodal.toml')
    assert 'judge_rounds' not in c['loop'] and 'dataset' not in c
