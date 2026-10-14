from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

def box(v):
    x,y,w,h = v
    if w <= 0 or h <= 0 or x+w > 1.000001 or y+h > 1.000001:
        raise ValueError('bbox must lie inside image and have positive size')
    return v
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
BBox = Annotated[list[Unit], Field(min_length=4,max_length=4), AfterValidator(box)]
Point = Annotated[list[Unit], Field(min_length=2,max_length=2)]
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
class Canvas(Strict):
    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]
class Node(Strict):
    id: str
    kind: Literal['shape','text','asset','junction']
    label: str
    bbox: BBox
    panel_id: str | None
    confidence: Unit
class Arrow(Strict):
    point: Point
    direction_vector: Annotated[list[float], Field(min_length=2,max_length=2)]
    segment_index: Annotated[int, Field(ge=0)]
class Edge(Strict):
    id: str
    source_id: str | None
    target_id: str | None
    direction: Literal['forward','backward','both','none','unknown']
    label: str
    polyline: Annotated[list[Point], Field(min_length=2)]
    arrowheads: list[Arrow]
    confidence: Unit
class Panel(Strict):
    id: str
    bbox: BBox
    label: str
class Uncertainty(Strict):
    id: str
    description: str
    bbox: BBox
    related_ids: list[str]
class DiagramSpec(Strict):
    schema_version: Literal[1]
    task_id: str
    canvas: Canvas
    nodes: list[Node]
    edges: list[Edge]
    panels: list[Panel]
    uncertainties: list[Uncertainty]
    @model_validator(mode='after')
    def references(self):
        objects = self.nodes + self.edges + self.panels
        ids = [x.id for x in objects]
        if len(ids) != len(set(ids)): raise ValueError('duplicate object IDs')
        nodes = {n.id for n in self.nodes}; panels = {p.id for p in self.panels}
        for n in self.nodes:
            if n.panel_id is not None and n.panel_id not in panels: raise ValueError('unknown panel')
        for e in self.edges:
            if any(i is not None and i not in nodes for i in (e.source_id,e.target_id)): raise ValueError('unknown endpoint')
            if any(a.segment_index >= len(e.polyline)-1 for a in e.arrowheads): raise ValueError('unknown segment')
            if (e.source_id is None or e.target_id is None or e.direction == 'unknown') and not any(e.id in u.related_ids for u in self.uncertainties):
                raise ValueError('uncertain edge must be recorded')
        return self
class AuthorResult(Strict):
    schema_version: Literal[1]
    entrypoint: Literal['build.py']
    spec_path: str
    changed_object_ids: list[str]
    change_summary: str
    unresolved: list[str]
class Issue(Strict):
    id: str
    stage: Literal['artifact','semantic','render','detail']
    issue_type: str
    severity: Literal['high','medium','low']
    reference_bbox: BBox | None
    candidate_bbox: BBox | None
    object_ids: list[str]
    observed: str
    expected: str
    repair_hint: str
    evidence_paths: list[str]
class ExploreRequest(Strict):
    image: Literal['reference','candidate']
    bbox: BBox
    scale: Annotated[float, Field(ge=1,le=4)]
    reason: str
class Feedback(Strict):
    schema_version: Literal[1]
    candidate_id: str
    action: Literal['revise','explore','done']
    issues: list[Issue]
    explore_requests: Annotated[list[ExploreRequest],Field(max_length=8)]
    preserve_ids: list[str]
    reason: str
class Probe(Strict):
    labels: list[str]
    wrote_file: bool
