from pathlib import Path
import hashlib, json, shutil
from .contracts import Evidence

def safe_path(root: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f'Not a relative artifact path: {relative}')
    result = root / p
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Artifact escapes workspace: {relative}')
    if any(x.is_symlink() for x in [result, *result.parents] if x != root.parent):
        raise ValueError('Symlink artifacts are not allowed')
    return result

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def manifest(root: Path) -> dict:
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError(f'Symlink in candidate: {p}')
        if p.is_file() and '.harness' not in p.relative_to(root).parts:
            result[p.relative_to(root).as_posix()] = sha(p)
    return result

def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def snapshot(source: Path, target: Path) -> dict:
    before = manifest(source)
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('.harness'))
    if manifest(target) != before or manifest(source) != before:
        raise ValueError('Candidate changed during snapshot')
    return before

def verify(root: Path, expected: dict):
    if manifest(root) != expected: raise ValueError('Frozen candidate has changed')

def evidence(path: Path, root: Path, kind: str, candidate: str) -> Evidence:
    relative = path.relative_to(root).as_posix()
    safe_path(root,relative)
    return Evidence(path=relative,sha256=sha(path),kind=kind,candidate_id=candidate)
