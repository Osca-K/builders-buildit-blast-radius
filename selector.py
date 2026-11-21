"""Select tests from a pristine-source coverage map; optimize worker overhead."""
import ast
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json
import os
from pathlib import Path
import re
import sys
import copy
from functools import lru_cache
from comparison_equivalence import equivalent_tests
from comparison_value_equivalence import equivalent_value_tests

HUNK=re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

@lru_cache(maxsize=128)
def source_tree(source):
    return ast.parse(source)

def changed_class_constants(before,after):
    """Only prune attribute users when every AST edit is a literal class value."""
    names=set()
    def literal(node):
        try:
            ast.literal_eval(node)
            return True
        except (ValueError,TypeError,SyntaxError,RecursionError):
            return False
    def normalize(tree):
        tree=copy.deepcopy(tree)
        for cls in ast.walk(tree):
            if not isinstance(cls,ast.ClassDef): continue
            for node in cls.body:
                if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and literal(node.value):
                    names.add(node.targets[0].id)
                    node.value=ast.Constant(value=None)
        return ast.dump(tree)
    if normalize(before)!=normalize(after): return set()
    # Keep only actual changes; unchanged class attributes must not broaden the map.
    old={}
    for node in ast.walk(before):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            old[(node.lineno,node.targets[0].id)]=ast.dump(node.value)
    changed=set()
    for node in ast.walk(after):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in names and old.get((node.lineno,name))!=ast.dump(node.value): changed.add(name)
    return changed

def changed_expression_schemas(before,after):
    """Locate exact literal arg_types declarations, retaining mixed-edit fallback."""
    if changed_class_constants(before,after) != {'arg_types'}:
        return None
    def schemas(tree):
        found={}
        def walk(body,prefix=''):
            for cls in body:
                if not isinstance(cls,ast.ClassDef):continue
                qualname=prefix+cls.name
                for node in cls.body:
                    if (isinstance(node,ast.Assign) and len(node.targets)==1
                            and isinstance(node.targets[0],ast.Name)
                            and node.targets[0].id=='arg_types'):
                        if qualname in found:return False
                        # Other literal shapes can raise in __init_subclass__
                        # during import, affecting tests without any schema read.
                        try:value=ast.literal_eval(node.value)
                        except (ValueError,TypeError,SyntaxError,RecursionError):return False
                        if (type(value) is not dict or any(type(k) is not str or type(v) is not bool
                                                          for k,v in value.items())):return False
                        found[qualname]=ast.dump(node.value)
                if walk(cls.body,qualname+'.') is False:return False
            return True
        return found if walk(tree.body) else None
    old,new=schemas(before),schemas(after)
    if old is None or new is None or old.keys()!=new.keys():return None
    return {name for name in old if old[name]!=new[name]}

def changed_dictionary_values(before,after):
    """Find value-only changes in literal class dictionaries with fixed keys."""
    if not changed_class_constants(before,after):return None
    def values(tree):
        found={}
        def walk(body,prefix=''):
            for cls in body:
                if not isinstance(cls,ast.ClassDef):continue
                qualname=prefix+cls.name
                for node in cls.body:
                    if (isinstance(node,ast.Assign) and len(node.targets)==1
                            and isinstance(node.targets[0],ast.Name)):
                        try:value=ast.literal_eval(node.value)
                        except (ValueError,TypeError,SyntaxError,RecursionError):continue
                        key=(qualname,node.targets[0].id)
                        if key in found:return False
                        found[key]=(value,ast.dump(node.value))
                if walk(cls.body,qualname+'.') is False:return False
            return True
        return found if walk(tree.body) else None
    old,new=values(before),values(after)
    if old is None or new is None or old.keys()!=new.keys():return None
    changed={}
    for key,(a,a_ast) in old.items():
        b,b_ast=new[key]
        if a_ast==b_ast:continue
        if (key[1]=='arg_types' or type(a) is not dict or type(b) is not dict
                or list(a)!=list(b) or any(type(k) is not str for k in a)):
            return None
        # Comparing literal values is side-effect-free, but Python equates some
        # distinct types (True/1); repr retains those distinctions conservatively.
        changed[key]=[k for k in a if repr(a[k])!=repr(b[k]) or type(a[k]) is not type(b[k])]
        if not changed[key]:return None
    return changed or None

def path_name(value):
    value=value.split('\t',1)[0]
    if value.startswith('"'):
        # Git C-quoted paths use octal escapes for UTF-8 bytes.
        value=ast.literal_eval('b'+value).decode('utf-8')
    return value[2:] if value.startswith(('a/','b/')) else value

def diff(text):
    changes=[];current=None;hunk=None;old=0;remaining_old=remaining_new=0;replacing=False
    for line in text.splitlines():
        m=HUNK.match(line)
        if m:
            if current is None: raise ValueError('hunk without file')
            old=int(m[1]);remaining_old=int(m[2] if m[2] is not None else 1);remaining_new=int(m[4] if m[4] is not None else 1)
            hunk={'start':old,'count':remaining_old,'body':[]};current['hunks'].append(hunk);replacing=False
            if remaining_old==0: old+=1  # A zero-length hunk inserts after its old start.
            continue
        if remaining_old or remaining_new:
            if line.startswith('\\'): continue
            if not line or line[0] not in ' +-': raise ValueError('bad hunk body')
            hunk['body'].append(line)
            if line[0]=='-': current['lines'].add(old);old+=1;remaining_old-=1;replacing=True
            elif line[0]=='+':
                # Replacement additions correspond to the removed old lines.
                # Mapping them to the next untouched line can select an unrelated
                # function or trigger a module-wide fallback at function end.
                if not replacing: current['lines'].update((max(1,old-1),old))
                remaining_new-=1
            else: old+=1;remaining_old-=1;remaining_new-=1;replacing=False
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
        neutral=0
        before=after=None
        if old==new and source is not None and ch['hunks']:
            try:
                before=source_tree(source);after=ast.parse(patched(source,ch))
                if ast.dump(before)==ast.dump(after): continue
                neutral=equivalent_tests(before,after,index,old)|equivalent_value_tests(before,after,index,old)
            except SyntaxError:
                # Syntax errors can prevent collection of all importing modules.
                return all_tests
            except (ValueError,TypeError): pass
        if any(p in {'pyproject.toml','pytest.ini','setup.cfg','setup.py','requirements.lock','conftest.py'} or p.endswith('/conftest.py') for p in paths):
            return all_tests
        owner=0
        for p in paths: owner|=int(index['owners'].get(p,'0'),16)
        if owner:
            selected|=owner&~neutral;continue
        lm=index['lines'].get(old,{})
        hit=0
        for n in ch['lines']: hit|=int(lm.get(str(n),'0'),16)
        # Module/class initialization and uncovered definitions need all file users.
        module_level=False
        if source and old and old.endswith('.py'):
            try:
                tree=source_tree(source)
                functions=[(n.lineno,n.end_lineno) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
                module_level=any(not any(a<=n<=b for a,b in functions) for n in ch['lines'])
            except SyntaxError: module_level=True
        if module_level:
            # Expression schemas derive required_args during class creation.
            # The pristine schema trace maps both direct and derived reads to
            # their exact declaring class; a complete map can represent no reads.
            schemas=(changed_expression_schemas(before,after)
                     if before is not None and after is not None
                     and index.get('class_attribute_complete')
                     and old in index.get('class_schema_paths',()) else None)
            if schemas:
                users=0
                for qualname in schemas:
                    users|=int(index.get('class_attributes',{}).get(f'{old}:{qualname}:arg_types','0'),16)
                selected|=users&~neutral
                continue
            dictionaries=(changed_dictionary_values(before,after)
                          if before is not None and after is not None
                          and index.get('dictionary_reads_complete')
                          and index.get('dictionary_external_calls_traced') else None)
            if dictionaries:
                origins={f'{old}:{qualname}:{name}':keys
                         for (qualname,name),keys in dictionaries.items()}
                if all(origin in index.get('dictionary_origins',()) for origin in origins):
                    users=0
                    for origin,keys in origins.items():
                        reads=index.get('dictionary_reads',{}).get(origin,{})
                        users|=int(reads.get('*','0'),16)
                        for key in keys:
                            token='key:'+json.dumps(key,ensure_ascii=True,separators=(',',':'))
                            users|=int(reads.get(token,'0'),16)
                    selected|=users&~neutral
                    continue
            # Class constants are executed at import, so line coverage selects
            # every importer. Attribute tracing identifies the tests that
            # actually read the changed constant.
            attribute_mask=0
            if source and old:
                for node in ast.walk(tree):
                    if not isinstance(node,(ast.Assign,ast.AnnAssign)) or not hasattr(node,'end_lineno'):
                        continue
                    if not any(node.lineno<=n<=node.end_lineno for n in ch['lines']):
                        continue
                    targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target,ast.Name):
                            attribute_mask|=int(index.get('attributes',{}).get(f'{old}:{target.id}','0'),16)
            constant_names=changed_class_constants(before,after) if before is not None and after is not None and index.get('attribute_declarations') else set()
            complete=constant_names and all(index.get('attributes',{}).get(f'{old}:{name}') for name in constant_names)
            if attribute_mask and complete:
                selected|=attribute_mask&~neutral
                continue
            # The pristine build records actual dialect/parser/generator
            # receiver modules, including inherited class-flag accesses.
            users=0
            for p in paths: users|=int(index['files'].get(p,'0'),16)
            selected|=(users or all_tests)&~neutral
            continue
        # Coverage attributes a multiline expression to its statement header.
        # Include that header, but not every unrelated branch in the function.
        if source and old and old.endswith('.py'):
            tree=source_tree(source)
            headers=(ast.If,ast.While,ast.IfExp,ast.BoolOp,ast.Compare,ast.Call,
                     ast.Assign,ast.AnnAssign,ast.Return)
            nodes=[node for node in ast.walk(tree) if isinstance(node,headers) and hasattr(node,'end_lineno')]
            for n in ch['lines']:
                boolean=[node for node in nodes if isinstance(node,ast.BoolOp) and node.lineno<=n<=node.end_lineno]
                if boolean:
                    node=min(boolean,key=lambda node:node.end_lineno-node.lineno)
                    for line in range(node.lineno,node.end_lineno+1):
                        hit|=int(lm.get(str(line),'0'),16)
                enclosing=[node for node in nodes if node.lineno<=n<=node.end_lineno]
                if enclosing:
                    node=min(enclosing,key=lambda node:node.end_lineno-node.lineno)
                    hit|=int(lm.get(str(node.lineno),'0'),16)
        else:
            for p in paths: hit |= int(index['files'].get(p,'0'),16)

        if not hit and source and old and old.endswith('.py'):
            funcs=[node for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
            for n in ch['lines']:
                enclosing=[node for node in funcs if node.lineno<=n<=node.end_lineno]
                if enclosing:
                    node=min(enclosing,key=lambda node:node.end_lineno-node.lineno)
                    for line in range(node.lineno,node.end_lineno+1):
                        hit|=int(lm.get(str(line),'0'),16)
        if not hit: return all_tests
        selected|=hit&~neutral
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
    probes=None
    if os.environ.get('PROBE_MODE','off')!='off':
        from runtime_probe import Probes
        probes=Probes()
    catalog_matches=index is not None and set(by_id).issubset(index['tests'])
    for patch in sorted((root/'commits').glob('*.patch')):
        if catalog_matches:
            patch_text=patch.read_text(encoding='utf-8')
            mask=choose(index,patch_text)
            selected=[]
            while mask:
                bit=mask&-mask
                item=by_id.get(index['tests'][bit.bit_length()-1])
                if item is not None: selected.append(item)
                mask^=bit
            if probes is not None:selected=probes.filter(index,patch_text,selected)
        else:
            # Correct fallback when the build coverage index is absent/incompatible.
            selected=tests
        print(json.dumps({'commit':patch.stem,'workers':schedule(selected)},separators=(',',':')))
    if not catalog_matches: print('Using all-tests fallback: no compatible coverage index',file=sys.stderr)
    if probes is not None:probes.finish()

if __name__=='__main__': main()
