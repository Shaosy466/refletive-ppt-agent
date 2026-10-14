from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

class HarnessError(RuntimeError):
    kind = "INFRA_ERROR"
class ConfigError(HarnessError):
    kind = "CONFIG_ERROR"
class InputError(HarnessError):
    kind = "INPUT_ERROR"
class BudgetExhausted(HarnessError):
    kind = "BUDGET_EXHAUSTED"

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def read_json(path: Path):
    return json.loads(path.read_text())

def inside(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise InputError(f'Unsafe relative path: {relative}')
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise InputError(f'Path escapes root: {relative}')
    return target

def tree_hash(root: Path):
    return digest({str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
                   if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts})

def snapshot_hashes(root: Path):
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise InputError(f'Symlink prohibited in snapshot: {p}')
        if p.is_file() and '__pycache__' not in p.parts: files[str(p.relative_to(root))] = sha(p)
    return files
