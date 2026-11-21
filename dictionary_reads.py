"""Build-only value-read contexts for pristine literal class dictionaries."""
import json
import functools

observations={}
origins=set()
context=lambda:''
_json_wrapped=False
_key_tokens={}


def key_token(key):
    if type(key) is str:
        token=_key_tokens.get(key)
        if token is None:
            token='key:'+json.dumps(key,ensure_ascii=True,separators=(',',':'))
            _key_tokens[key]=token
        return token
    try:return 'key:'+json.dumps(key,ensure_ascii=True,separators=(',',':'))
    except (TypeError,ValueError):return '*'


class ObservedDict(dict):
    def __init__(self,value,origin):
        super().__init__(value)
        self._rwx_origin=origin
        origins.add(origin)

    def record(self,key=None):
        token='*' if key is None else key_token(key)
        observations.setdefault(self._rwx_origin,{}).setdefault(token,set()).add(context() or 'unscoped')

    def __getitem__(self,key):
        self.record(key)
        return super().__getitem__(key)

    def get(self,key,default=None):
        self.record(key)
        return super().get(key,default)

    def pop(self,key,*default):
        self.record(key)
        return super().pop(key,*default)

    def setdefault(self,key,default=None):
        self.record(key)
        return super().setdefault(key,default)

    def popitem(self):
        self.record()
        return super().popitem()

    def update(self,*args,**kwargs):
        if args and isinstance(args[0],ObservedDict):args[0].record()
        return super().update(*args,**kwargs)

    def __reduce_ex__(self,protocol):
        self.record()
        return super().__reduce_ex__(protocol)

    def values(self):
        self.record()
        return super().values()

    def items(self):
        self.record()
        return super().items()

    def __iter__(self):
        # Keeping this override makes dict(observed) route through keys and
        # __getitem__, rather than silently copying its internal value table.
        return super().__iter__()

    def copy(self):
        return ObservedDict(super().copy(),self._rwx_origin)

    def __or__(self,other):
        self.record()
        if isinstance(other,ObservedDict):other.record()
        return super().__or__(other)

    def __ror__(self,other):
        self.record()
        if isinstance(other,ObservedDict):other.record()
        return super().__ror__(other)

    def __eq__(self,other):
        self.record()
        if isinstance(other,ObservedDict):other.record()
        return super().__eq__(other)

    def __ne__(self,other):
        self.record()
        if isinstance(other,ObservedDict):other.record()
        return super().__ne__(other)

    def __repr__(self):
        self.record()
        return super().__repr__()

    __str__=__repr__


def track(value,origin):
    return ObservedDict(value,origin)


def base_method(owner,name):
    # Explicit calls such as dict.__getitem__(observed,key) otherwise bypass
    # subclass overrides. Any observed mapping passed to a base method is a
    # conservative wildcard dependency.
    function=getattr(owner,name)
    @functools.wraps(function)
    def wrapped(*args,**kwargs):
        if owner is dict:
            for value in (*args,*kwargs.values()):
                if isinstance(value,ObservedDict):value.record()
        return function(*args,**kwargs)
    return wrapped


def mark_serialized(value,seen=None):
    if seen is None:seen=set()
    if id(value) in seen:return
    seen.add(id(value))
    if isinstance(value,ObservedDict):value.record()
    if isinstance(value,dict):
        for child in dict.values(value):mark_serialized(child,seen)
    elif isinstance(value,(list,tuple)):
        for child in value:mark_serialized(child,seen)


def call(function,*args,**kwargs):
    """Observe dictionaries escaping to consumers outside instrumented Python."""
    code=getattr(function,'__code__',None)
    module=getattr(function,'__module__','') or ''
    owner=getattr(function,'__self__',None)
    pristine=(module in ('dictionary_reads','class_attributes')
              or (code is not None and code.co_filename.startswith('/opt/sqlglot/'))
              or (isinstance(function,type) and module.startswith(('sqlglot','tests'))))
    if not pristine and not any(function is known for known in (len,bool,type,id,isinstance,issubclass)):
        if isinstance(owner,ObservedDict):owner.record()
        for value in args:mark_serialized(value)
        for value in kwargs.values():mark_serialized(value)
    return function(*args,**kwargs)


def _serialized(function,method=False):
    @functools.wraps(function)
    def wrapped(*args,**kwargs):
        position=1 if method else 0
        value=args[position] if len(args)>position else kwargs.get('obj',kwargs.get('o'))
        mark_serialized(value)
        return function(*args,**kwargs)
    return wrapped


def install(get_context):
    global context,_json_wrapped
    context=get_context
    if not _json_wrapped:
        json.dump=_serialized(json.dump)
        json.dumps=_serialized(json.dumps)
        json.JSONEncoder.encode=_serialized(json.JSONEncoder.encode,method=True)
        json.JSONEncoder.iterencode=_serialized(json.JSONEncoder.iterencode,method=True)
        _json_wrapped=True
