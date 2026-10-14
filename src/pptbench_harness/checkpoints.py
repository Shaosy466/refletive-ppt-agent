from __future__ import annotations
import fcntl, time, sys, ctypes

# mach_continuous_time includes host sleep, unlike macOS monotonic time.
if sys.platform == "darwin":
    _lib=ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    class _Timebase(ctypes.Structure):
        _fields_=[("numer",ctypes.c_uint32),("denom",ctypes.c_uint32)]
    _tb=_Timebase();_lib.mach_timebase_info(ctypes.byref(_tb))
    _lib.mach_continuous_time.restype=ctypes.c_uint64
    def clock():return _lib.mach_continuous_time()*_tb.numer/_tb.denom/1e9
elif hasattr(time,"CLOCK_BOOTTIME"):
    def clock():return time.clock_gettime(time.CLOCK_BOOTTIME)
else:
    clock=time.monotonic
from contextlib import contextmanager
from pathlib import Path
from .workspace import atomic_json, read_json, BudgetExhausted, ConfigError, sha

@contextmanager
def lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ConfigError(f'Already running: {path}')
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)

class Budget:
    def __init__(self, path: Path, limits: dict):
        self.path=path; self.limits=limits
        d=read_json(path) if path.exists() else {}
        self.usage_complete=d.get('usage_complete',True)
        self.calls=d.get('calls',0); self.spent=d.get('elapsed_seconds',0.0)
        self.started=clock()
        # Reserve the full in-flight timeout on hard crash; graceful completion reconciles it.
        self.spent += d.get('reserved_seconds',0)
        self.reserved=0
    @property
    def elapsed(self): return self.spent + clock()-self.started
    @property
    def remaining(self): return max(0,self.limits['task_timeout_seconds']-self.elapsed)
    def check(self, call=False):
        if self.remaining <= 0 or (call and self.calls >= self.limits['max_agent_calls']):
            raise BudgetExhausted('Task time or agent call budget exhausted')
    def begin(self, timeout):
        self.check(call=True); self.calls+=1
        self.reserved=min(timeout,self.remaining); self.save()
        return self.reserved
    def save(self):
        atomic_json(self.path,{'usage_complete':self.usage_complete,'calls':self.calls,'elapsed_seconds':self.elapsed,'reserved_seconds':self.reserved})
    def finish(self): self.reserved=0; self.save()

def commit(path: Path, payload, files: list[Path]):
    atomic_json(path,{'payload':payload,'files':{str(p.resolve()):sha(p) for p in files}})

def restore(path: Path):
    if not path.exists(): return None
    d=read_json(path)
    for p,h in d['files'].items():
        if not Path(p).is_file() or sha(Path(p)) != h: raise ConfigError(f'Checkpoint artifact changed: {p}')
    return d['payload']
