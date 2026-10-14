from __future__ import annotations
from typing import Literal, Protocol
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1

class Task(Record):
    benchmark: str
    case_id: str
    revision: str
    instruction: str
    kind: Literal['artifact', 'episode', 'edit_chain'] = 'artifact'
    public_dir: str
    output_contract: str
    protocol: str = 'development'
    seed: int = 0

class Evidence(Record):
    path: str
    sha256: str
    kind: Literal['image', 'video', 'log', 'state', 'trace']
    candidate_id: str

class Finding(Record):
    observed: str
    expected: str
    evidence: list[str]
    repair: str

class Review(Record):
    decision: Literal['done', 'revise', 'explore']
    findings: list[Finding]
    summary: str

class Execution(Record):
    ok: bool
    evidence: list[Evidence] = Field(default_factory=list)
    public_feedback: dict = Field(default_factory=dict)

class Metric(Record):
    value: float | None
    unit: str
    direction: Literal['higher', 'lower']
    status: Literal['ok', 'not_applicable', 'error', 'unavailable']

class Evaluation(Record):
    complete: bool
    protocol: str
    metrics: dict[str, Metric] = Field(default_factory=dict)
    details: dict = Field(default_factory=dict)
    official_comparable: bool = False

class Adapter(Protocol):
    name: str
    def doctor(self) -> dict: ...
    def prepare(self, case_id: str, destination: Path) -> Task: ...
    async def execute(self, task: Task, workspace: Path, evidence_dir: Path, candidate_id: str) -> Execution: ...
    async def evaluate(self, task: Task, submission: Path, output: Path) -> Evaluation: ...


def strict_schema(model) -> dict:
    """Codex structured output requires every object property to be required."""
    schema=model.model_json_schema()
    def walk(node):
        if isinstance(node,dict):
            if node.get('type')=='object':
                node['additionalProperties']=False
                node['required']=list(node.get('properties',{}))
            node.pop('default',None)
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(schema)
    return schema
