"""Conservative identity/equality equivalence using pristine operand types."""
import ast

def neutral_types(pair):
    left,right=pair.split('|',1)
    if left=='none' or right=='none':
        other=right if left=='none' else left
        return other in ('none','identity') or other.startswith(('builtin:','enum:'))
    if left==right=='identity':
        return True
    # Primitive-backed enums can construct noncanonical equal-valued objects.
    # Type observations alone do not prove their identity/equality equivalent.
    return False

def equivalent_tests(before,after,index,path):
    if index.get('base_exit_code')!=0:return 0
    changes=[]
    def same(a,b):
        if type(a) is not type(b):return False
        if isinstance(a,ast.Compare) and len(a.ops)==len(b.ops)==1:
            pair={type(a.ops[0]),type(b.ops[0])}
            if pair in ({ast.Is,ast.Eq},{ast.IsNot,ast.NotEq}):
                if ast.dump(a.left)!=ast.dump(b.left) or ast.dump(a.comparators[0])!=ast.dump(b.comparators[0]):return False
                changes.append(f'{path}:{a.lineno}:{a.col_offset}')
                return True
        if isinstance(a,ast.AST):
            return all(same(getattr(a,k),getattr(b,k)) for k in a._fields)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        return a==b
    if not same(before,after) or not changes:return 0
    result=(1<<len(index['tests']))-1
    for location in changes:
        pairs=index.get('comparison_types',{}).get(location)
        if not pairs:return 0
        safe=unsafe=0
        for pair,value in pairs.items():
            if neutral_types(pair):safe|=int(value,16)
            else:unsafe|=int(value,16)
        result&=safe&~unsafe
    return result
