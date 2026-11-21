"""Build-only operand-type observations from unmodified pinned source.

No patches, mutation outcomes, expected failures, or test answers are read.
The import instrumentation preserves operand order and the comparison result.
"""
import ast
import enum
import importlib.abc
import importlib.machinery
import operator
from pathlib import Path
import sys

observations = {}
context = lambda: ''
_types = {}
_operators = {'Is': operator.is_, 'IsNot': operator.is_not,
              'Eq': operator.eq, 'NotEq': operator.ne}

def descriptor(value):
    cls = type(value)
    key = id(cls)
    if key in _types:
        return _types[key]
    eq = type.__getattribute__(cls, '__eq__')
    ne = type.__getattribute__(cls, '__ne__')
    if cls is type(None):
        result = 'none'
    elif cls in (bool, int, float, complex, str, bytes, list, tuple, dict, set, frozenset):
        result = 'builtin:' + cls.__name__
    elif eq is object.__eq__ and ne is object.__ne__:
        result = 'identity'
    elif isinstance(cls, enum.EnumMeta) and eq in (str.__eq__, int.__eq__, object.__eq__) and ne in (str.__ne__, int.__ne__, object.__ne__):
        result = 'enum:' + type.__getattribute__(cls, '__module__') + '.' + type.__getattribute__(cls, '__qualname__')
    else:
        result = 'other'
    _types[key] = result
    return result

def compare(location, op, left, right):
    current = context() or 'unscoped'
    pair = descriptor(left) + '|' + descriptor(right)
    observations.setdefault(location, {}).setdefault(pair, set()).add(current)
    return _operators[op](left, right)

class Rewrite(ast.NodeTransformer):
    def __init__(self, filename):
        self.filename = filename
    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) != 1 or type(node.ops[0]).__name__ not in _operators:
            return node
        location = f'{self.filename}:{node.lineno}:{node.col_offset}'
        return ast.copy_location(ast.Call(func=ast.Name(id='_rwx_compare', ctx=ast.Load()),
            args=[ast.Constant(location), ast.Constant(type(node.ops[0]).__name__),
                  node.left, node.comparators[0]], keywords=[]), node)

class Loader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        path = self.get_filename(fullname)
        tree = ast.parse(self.get_data(path), filename=path)
        relative = Path(path).relative_to('/opt/sqlglot').as_posix()
        tree = Rewrite(relative).visit(tree)
        pos = 0
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
            pos = 1
        while pos < len(tree.body) and isinstance(tree.body[pos], ast.ImportFrom) and tree.body[pos].module == '__future__':
            pos += 1
        tree.body.insert(pos, ast.ImportFrom(module='comparison_types', names=[ast.alias(name='compare', asname='_rwx_compare')], level=0))
        return compile(ast.fix_missing_locations(tree), path, 'exec')

class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'sqlglot' and not fullname.startswith('sqlglot.'):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec and isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            spec.loader = Loader(fullname, spec.origin)
        return spec

def install(get_context):
    global context
    context = get_context
    sys.meta_path.insert(0, Finder())
