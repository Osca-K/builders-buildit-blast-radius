"""Pristine declaration-scoped expression-schema dependencies.

Only reads are observed. The wrapped attribute lookup returns the original value,
and no incoming patches or test outcomes are read by this collector.
"""
observations = {}
context = lambda: ''
_owners = {}


def read(owner, name, derived=False):
    value = getattr(owner, name)
    cls = owner if isinstance(owner, type) else type(owner)
    cache_key = (cls, name)
    if cache_key not in _owners:
        key = None
        # Expr.__init_subclass__ derives required_args from arg_types. A later
        # required_args read depends on that same schema declaration.
        declared = 'arg_types' if name == 'required_args' else name
        for base in type.__getattribute__(cls, '__mro__'):
            if declared in vars(base):
                module = type.__getattribute__(base, '__module__')
                if module.startswith('sqlglot.'):
                    key = module.replace('.', '/') + '.py:' + type.__getattribute__(base, '__qualname__') + ':arg_types'
                break
        _owners[cache_key] = key
    key = _owners[cache_key]
    current = context()
    if key and (current or not derived):
        observations.setdefault(key, set()).add(current or 'unscoped')
    return value


def install(get_context):
    global context
    context = get_context
