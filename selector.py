"""Select tests from a pristine-source coverage map; optimize worker overhead."""
import ast
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json
import os
from pathlib import Path
import re
import sys

HUNK=re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

def path_name(value):
    value=value.split('\t',1)[0]
    if value.startswith('"'):
        # Git C-quoted paths use octal escapes for UTF-8 bytes.
        value=ast.literal_eval('b'+value).decode('utf-8')
    return value[2:] if value.startswith(('a/','b/')) else value

def diff(text):
    changes=[];current=None;hunk=None;old=0;remaining_old=remaining_new=0
    for line in text.splitlines():
        m=HUNK.match(line)
        if m:
            if current is None: raise ValueError('hunk without file')
            old=int(m[1]);remaining_old=int(m[2] if m[2] is not None else 1);remaining_new=int(m[4] if m[4] is not None else 1)
            hunk={'start':old,'count':remaining_old,'body':[]};current['hunks'].append(hunk)
            continue
        if remaining_old or remaining_new:
            if line.startswith('\\'): continue
            if not line or line[0] not in ' +-': raise ValueError('bad hunk body')
            hunk['body'].append(line)
            if line[0]=='-': current['lines'].add(old);old+=1;remaining_old-=1
            elif line[0]=='+': current['lines'].update((max(1,old-1),old));remaining_new-=1
            else: old+=1;remaining_old-=1;remaining_new-=1
            continue
        if line.startswith('diff --git '):
            current={'old':None,'new':None,'lines':set(),'hunks':[]};changes.append(current)
        elif line.startswith('--- '):
            if current is None:
                current={'old':None,'new':None,'lines':set(),'hunks':[]};changes.append(current)
            current['old']=path_name(line[4:])
        elif line.startswith('+++ '): current['new']=path_name(line[4:])
    if remaining_old or remaining_new: raise ValueError('truncated hunk')
    return changes

def patched(source,change):
    lines=source.splitlines(keepends=True);out=[];cursor=0
    for h in change['hunks']:
        start=h['start']-1 if h['count'] else h['start']
        if start<cursor: raise ValueError('overlap')
        out.extend(lines[cursor:start]);cursor=start
        for line in h['body']:
            if line[0] in ' -':
                if cursor>=len(lines) or lines[cursor].rstrip('\n\r')!=line[1:]: raise ValueError('source mismatch')
                cursor+=1
            if line[0] in ' +': out.append(line[1:]+'\n')
    out.extend(lines[cursor:]);return ''.join(out)

def choose(index,text):
    all_tests=(1<<len(index['tests']))-1
    selected=0
    try: changes=diff(text)
    except (ValueError,SyntaxError): return all_tests
    if not changes: return all_tests
    for ch in changes:
        old,new=ch['old'],ch['new']
        paths={p for p in (old,new) if p and p!='/dev/null'}
        if not paths: return all_tests
        source=index['sources'].get(old)
        if old==new and source is not None and ch['hunks']:
            try:
                before=ast.parse(source);after=ast.parse(patched(source,ch))
                if ast.dump(before)==ast.dump(after): continue
            except SyntaxError:
                # Syntax errors can prevent collection of all importing modules.
                return all_tests
            except (ValueError,TypeError): pass
        if any(p in {'pyproject.toml','pytest.ini','setup.cfg','setup.py','requirements.lock','conftest.py'} or p.endswith('/conftest.py') for p in paths):
            return all_tests
        owner=0
        for p in paths: owner|=int(index['owners'].get(p,'0'),16)
        if owner:
            selected|=owner;continue
        lm=index['lines'].get(old,{})
        hit=0
        for n in ch['lines']: hit|=int(lm.get(str(n),'0'),16)
        # Module/class initialization and uncovered definitions need all file users.
        module_level=False
        if source and old and old.endswith('.py'):
            try:
                tree=ast.parse(source)
                functions=[(n.lineno,n.end_lineno) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
                module_level=any(not any(a<=n<=b for a,b in functions) for n in ch['lines'])
            except SyntaxError: module_level=True
        if module_level:
            # Class flags and registries can be consumed by inherited code in
            # other modules without executing a line in the defining module.
            selected|=all_tests
            continue
        # A changed branch may newly affect callers which did not take that
        # branch on the pristine checkout. Retain all observed file callers.
        for p in paths: hit|=int(index['files'].get(p,'0'),16)
        if not hit: return all_tests
        selected|=hit
    return selected

def schedule(tests):
    if not tests: return []
    tests=sorted(tests,key=lambda t:(-t['ms'],t['number']))
    best=None
    for count in range(1,min(8,len(tests))+1):
        groups=[[] for _ in range(count)];loads=[0]*count
        for t in tests:
            i=min(range(count),key=loads.__getitem__)
            groups[i].append(t['number']);loads[i]+=t['ms']
        cost=max(loads)+2000*count
        if best is None or cost<best[0]: best=(cost,groups)
    return best[1]

def main():
    root=Path(os.environ.get('DATA_DIR','/data'))
    index_path=Path(os.environ.get('INDEX_PATH',str(Path(__file__).with_name('index.json.gz'))))
    tests=json.loads((root/'tests.json').read_text())['tests']
    for t in tests: t['ms']=int((Decimal(str(t['seconds']))*1000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    index=None
    if index_path.exists():
        with gzip.open(index_path,'rt',encoding='utf-8') as f: index=json.load(f)
    by_id={t['id']:t for t in tests}
    catalog_matches=index is not None and set(by_id).issubset(index['tests'])
    for patch in sorted((root/'commits').glob('*.patch')):
        if catalog_matches:
            mask=choose(index,patch.read_text(encoding='utf-8'))
            selected=[]
            while mask:
                bit=mask&-mask
                item=by_id.get(index['tests'][bit.bit_length()-1])
                if item is not None: selected.append(item)
                mask^=bit
        else:
            # Correct fallback when the build coverage index is absent/incompatible.
            selected=tests
        print(json.dumps({'commit':patch.stem,'workers':schedule(selected)},separators=(',',':')))
    if not catalog_matches: print('Using all-tests fallback: no compatible coverage index',file=sys.stderr)

if __name__=='__main__': main()
