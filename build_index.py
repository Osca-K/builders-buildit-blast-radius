"""Collect a line/resource-to-test map from the pristine pinned source only."""
import ast
import gzip
import json
import os
from pathlib import Path
import sys
import coverage
import pytest
import concurrent.futures
import pickle

# Trace worker work in the same process during map generation. The pristine
# tests use pools for throughput, and coverage contexts must include that work.
# Keep this build-only: runtime selection never executes the patched tests.
class CoveragePool(concurrent.futures.ThreadPoolExecutor):
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kwargs):
        super().__init__(max_workers=2, initializer=initializer, initargs=initargs)

    def submit(self, fn, /, *args, **kwargs):
        # Process pools serialize both requests and results. Preserving that
        # behavior is essential: sqlglot expressions serialize through serde.
        fn,args,kwargs=pickle.loads(pickle.dumps((fn,args,kwargs)))
        return super().submit(self.transport,fn,args,kwargs)

    @staticmethod
    def transport(fn,args,kwargs):
        return pickle.loads(pickle.dumps(fn(*args,**kwargs)))

concurrent.futures.ProcessPoolExecutor=CoveragePool

ROOT=Path('/opt/sqlglot')
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['SKIP_INTEGRATION']='0'
cov=coverage.Coverage(source=[str(ROOT/'sqlglot'),str(ROOT/'tests')],config_file=False,data_file=None)
ids=[]; owners={}; fixtures={}; accesses={}; context=''

def rel(path):
    try: return Path(path).resolve().relative_to(ROOT).as_posix()
    except (TypeError,ValueError,OSError): return None

def switch(name):
    global context
    old=context;context=name;cov.switch_context(name);return old

def key(f):
    return 'fixture:'+str(rel(f.func.__code__.co_filename) if hasattr(f.func,'__code__') else '')+':'+f.argname+':'+str(f.baseid)

def audit(event,args):
    if event=='open' and args and isinstance(args[0],(str,bytes)):
        p=rel(os.fsdecode(args[0]))
        if p and not p.startswith(('.git/','.pytest_cache/')) and not p.endswith(('.py','.pyc')):
            ctx=context
            if not ctx:
                frame=sys._getframe(1)
                while frame:
                    owner=rel(frame.f_code.co_filename)
                    if owner and owner.startswith('tests/') and owner.endswith('.py'):
                        ctx='owner:'+owner;break
                    frame=frame.f_back
            if ctx: accesses.setdefault(p,set()).add(ctx)

sys.addaudithook(audit)

class Plugin:
    def pytest_collection_modifyitems(self,items):
        for item in items:
            ids.append(item.nodeid);owners[item.nodeid]=rel(item.path)
            info=getattr(item,'_fixtureinfo',None)
            if info:
                for name in info.names_closure:
                    for f in info.name2fixturedefs.get(name) or []:
                        fixtures.setdefault(key(f),set()).add(item.nodeid)

    @pytest.hookimpl(wrapper=True,tryfirst=True)
    def pytest_runtest_protocol(self,item,nextitem):
        old=switch('test:'+item.nodeid)
        try: return (yield)
        finally: switch(old)

    @pytest.hookimpl(wrapper=True,tryfirst=True)
    def pytest_fixture_setup(self,fixturedef,request):
        old=switch(key(fixturedef))
        try: return (yield)
        finally: switch(old)

cov.start()
code=pytest.main(['tests','-q','-p','no:cacheprovider'],plugins=[Plugin()])
cov.stop()
if code not in (0,1) or not ids:
    raise SystemExit(f'Coverage collection failed: {code}, {len(ids)} tests')
ids=sorted(set(ids));positions={s:i for i,s in enumerate(ids)}
masks={'test:'+s:1<<i for s,i in positions.items()}
owner_masks={}
for s,p in owners.items(): owner_masks[p]=owner_masks.get(p,0)|(1<<positions[s])
masks.update({'owner:'+p:m for p,m in owner_masks.items()})
for ctx,users in fixtures.items():
    masks[ctx]=sum(1<<positions[s] for s in users)
lines={};files={}
data=cov.get_data()
for path in data.measured_files():
    p=rel(path)
    if not p: continue
    lm={};fm=0
    for n,contexts in data.contexts_by_lineno(path).items():
        mask=0
        for ctx in contexts: mask|=masks.get(ctx,0)
        if mask: lm[str(n)]=format(mask,'x');fm|=mask
    if lm: lines[p]=lm
    if fm: files[p]=fm
for p,contexts in accesses.items():
    mask=0
    for ctx in contexts: mask|=masks.get(ctx,0)
    files[p]=files.get(p,0)|mask
for p,m in owner_masks.items(): files[p]=files.get(p,0)|m
sources={}
for p in ROOT.rglob('*.py'):
    if '.git' not in p.parts:
        sources[p.relative_to(ROOT).as_posix()]=p.read_text(encoding='utf-8')
result={'tests':ids,'lines':lines,'files':{p:format(m,'x') for p,m in files.items()},
        'owners':{p:format(m,'x') for p,m in owner_masks.items()},'sources':sources,
        'base_exit_code':int(code),'base_commit':'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'}
with gzip.open('/app/index.json.gz','wt',encoding='utf-8') as f:
    json.dump(result,f,separators=(',',':'))
print(f'Indexed {len(ids)} tests, {len(files)} files',file=sys.stderr)
