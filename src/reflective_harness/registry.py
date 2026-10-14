from importlib.metadata import entry_points

_FACTORIES = {}

def register(name, factory):
    if name in _FACTORIES: raise ValueError(f'Duplicate adapter: {name}')
    _FACTORIES[name] = factory

def discover():
    from . import adapters
    adapters.register_builtins()
    for ep in entry_points(group='reflective_harness.adapters'):
        if ep.name not in _FACTORIES: register(ep.name,ep.load())
    return dict(_FACTORIES)

def get(name, root):
    factories = discover()
    if name not in factories: raise ValueError(f'Unknown benchmark {name}; choose {list(factories)}')
    return factories[name](root)
