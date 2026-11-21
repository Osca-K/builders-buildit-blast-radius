"""Supplement an existing pristine coverage index with schema/value reads only."""
import concurrent.futures
import gzip
import json
import os
from pathlib import Path
import pickle
import sys
import pytest

ROOT=Path('/opt/sqlglot')
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['SKIP_INTEGRATION']='0'
os.environ['RWX_SCHEMA_ONLY']='1'
PRIMITIVE_ONLY=os.environ.get('RWX_PRIMITIVE_ONLY')=='1'

class CoveragePool(concurrent.futures.ThreadPoolExecutor):
    def __init__(self,max_workers=None,mp_context=None,initializer=None,initargs=(),**kwargs):
        super().__init__(max_workers=2,initializer=initializer,initargs=initargs)
    def submit(self,fn,/,*args,**kwargs):
        fn,args,kwargs=pickle.loads(pickle.dumps((fn,args,kwargs)))
        return super().submit(self.transport,fn,args,kwargs)
    @staticmethod
    def transport(fn,args,kwargs):
        return pickle.loads(pickle.dumps(fn(*args,**kwargs)))
concurrent.futures.ProcessPoolExecutor=CoveragePool

context=''
ids=[]
fixtures={}

def relative(path):
    try:return Path(path).resolve().relative_to(ROOT).as_posix()
    except (TypeError,ValueError,OSError):return ''

def fixture_key(f):
    return 'fixture:'+str(relative(f.func.__code__.co_filename) if hasattr(f.func,'__code__') else '')+':'+f.argname+':'+str(f.baseid)

class Plugin:
    def pytest_collection_modifyitems(self,items):
        for item in items:
            ids.append(item.nodeid)
            info=getattr(item,'_fixtureinfo',None)
            if info:
                for name in info.names_closure:
                    for f in info.name2fixturedefs.get(name) or []:
                        fixtures.setdefault(fixture_key(f),set()).add(item.nodeid)
    @pytest.hookimpl(wrapper=True,tryfirst=True)
    def pytest_runtest_protocol(self,item,nextitem):
        global context
        previous=context;context='test:'+item.nodeid
        try:return (yield)
        finally:context=previous
    @pytest.hookimpl(wrapper=True,tryfirst=True)
    def pytest_fixture_setup(self,fixturedef,request):
        global context
        previous=context;context=fixture_key(fixturedef)
        try:return (yield)
        finally:context=previous

if PRIMITIVE_ONLY:
    import primitive_comparisons
    primitive_comparisons.install(lambda:context)
else:
    import comparison_types
    import class_attributes
    import dictionary_reads
    class_attributes.install(lambda:context)
    dictionary_reads.install(lambda:context)
    comparison_types.install(lambda:context)

with gzip.open('/app/base-index.json.gz','rt',encoding='utf-8') as handle:index=json.load(handle)
code=pytest.main(['tests','-q','-p','no:cacheprovider'],plugins=[Plugin()])
complete=int(code)==0 and set(ids)==set(index['tests'])
positions={name:i for i,name in enumerate(index['tests'])}
masks={'test:'+name:1<<i for name,i in positions.items()}
masks['unscoped']=(1<<len(positions))-1
for ctx,users in fixtures.items():
    masks[ctx]=sum(1<<positions[name] for name in users if name in positions)

def context_mask(contexts):
    value=0
    for ctx in contexts:value|=masks.get(ctx,0)
    return format(value,'x')

if PRIMITIVE_ONLY:
    index['comparison_values']={location:{key:context_mask(contexts) for key,contexts in pairs.items()}
                                for location,pairs in primitive_comparisons.observations.items()}
    index['comparison_value_unknown']={location:context_mask(contexts) for location,contexts in primitive_comparisons.unknown.items()}
    index['comparison_value_locations']=sorted(primitive_comparisons.locations)
    index['comparison_values_complete']=complete
    index['comparison_collection_exit_code']=int(code)
else:
    index['class_attributes']={key:context_mask(contexts) for key,contexts in class_attributes.observations.items()}
    index['class_attribute_complete']=complete
    index['class_schema_paths']=[p for p in index['sources'] if p.startswith('sqlglot/expressions/')]
    index['dictionary_reads']={origin:{key:context_mask(contexts) for key,contexts in keys.items()}
                               for origin,keys in dictionary_reads.observations.items()}
    index['dictionary_origins']=sorted(dictionary_reads.origins)
    index['dictionary_reads_complete']=complete
    index['dictionary_external_calls_traced']=complete
    index['schema_collection_exit_code']=int(code)
with gzip.open('/app/index.json.gz','wt',encoding='utf-8') as handle:json.dump(index,handle,separators=(',',':'))
print(f'Pristine supplemental collection complete={complete}, tests={len(ids)}, primitive={PRIMITIVE_ONLY}',file=sys.stderr)
