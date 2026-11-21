"""Observe bounded immutable comparison inputs on the pristine source only."""
import ast
import importlib.abc
import importlib.machinery
import json
import math
import operator
from pathlib import Path
import sys

OPERATORS={name:getattr(operator,attribute) for name,attribute in (
    ('Eq','eq'),('NotEq','ne'),('Lt','lt'),('LtE','le'),('Gt','gt'),('GtE','ge'))}
observations={}
unknown={}
locations=set()
context=lambda:''
MAX_PAIRS=128


def pack(value,depth=0):
    kind=type(value)
    if value is None:return ['none']
    if kind is bool:return ['bool',value]
    if kind is int and -(1<<63)<=value<(1<<63):return ['int',value]
    if kind is float and math.isfinite(value):return ['float',value]
    if kind is str and len(value)<=64:return ['str',value]
    if kind is bytes and len(value)<=64:return ['bytes',value.hex()]
    if kind is tuple and depth<2 and len(value)<=4:
        children=[pack(child,depth+1) for child in value]
        if all(child is not None for child in children):return ['tuple',children]
    return None


def unpack(value):
    kind=value[0]
    if kind=='none':return None
    if kind=='bytes':return bytes.fromhex(value[1])
    if kind=='tuple':return tuple(unpack(child) for child in value[1])
    if kind in ('bool','int','float','str'):return value[1]
    raise ValueError('unknown primitive')


def compare(location,op,left,right):
    current=context() or 'unscoped'
    try:result=OPERATORS[op](left,right)
    except BaseException:
        unknown.setdefault(location,set()).add(current)
        raise
    a,b=pack(left),pack(right)
    if a is None or b is None or type(result) is not bool:
        unknown.setdefault(location,set()).add(current)
        return result
    key=json.dumps([op,a,b,result],ensure_ascii=True,separators=(',',':'))
    pairs=observations.setdefault(location,{})
    if key not in pairs and len(pairs)>=MAX_PAIRS:
        unknown.setdefault(location,set()).add(current)
    else:pairs.setdefault(key,set()).add(current)
    return result


class Rewrite(ast.NodeTransformer):
    def __init__(self,path):self.path=path
    def visit_Compare(self,node):
        self.generic_visit(node)
        if len(node.ops)!=1 or type(node.ops[0]).__name__ not in OPERATORS:return node
        location=f'{self.path}:{node.lineno}:{node.col_offset}'
        locations.add(location)
        return ast.copy_location(ast.Call(func=ast.Name(id='_rwx_primitive_compare',ctx=ast.Load()),
            args=[ast.Constant(location),ast.Constant(type(node.ops[0]).__name__),node.left,node.comparators[0]],keywords=[]),node)


class Loader(importlib.machinery.SourceFileLoader):
    def get_code(self,fullname):
        path=self.get_filename(fullname)
        tree=Rewrite(Path(path).relative_to('/opt/sqlglot').as_posix()).visit(ast.parse(self.get_data(path),filename=path))
        position=0
        if tree.body and isinstance(tree.body[0],ast.Expr) and isinstance(tree.body[0].value,ast.Constant) and isinstance(tree.body[0].value.value,str):position=1
        while position<len(tree.body) and isinstance(tree.body[position],ast.ImportFrom) and tree.body[position].module=='__future__':position+=1
        tree.body.insert(position,ast.ImportFrom(module='primitive_comparisons',names=[ast.alias(name='compare',asname='_rwx_primitive_compare')],level=0))
        return compile(ast.fix_missing_locations(tree),path,'exec')


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname!='sqlglot' and not fullname.startswith('sqlglot.'):return None
        spec=importlib.machinery.PathFinder.find_spec(fullname,path,target)
        if spec and isinstance(spec.loader,importlib.machinery.SourceFileLoader):spec.loader=Loader(fullname,spec.origin)
        return spec


def install(get_context):
    global context
    context=get_context
    sys.meta_path.insert(0,Finder())
