"""Build-only value-read contexts for pristine literal class dictionaries."""
import json

observations={}
origins=set()
context=lambda:''


def key_token(key):
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


def install(get_context):
    global context
    context=get_context
