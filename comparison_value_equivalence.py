"""Prove comparison-only edits neutral for pristine observed primitive inputs."""
import ast
import json
from primitive_comparisons import OPERATORS,pack,unpack


def equivalent_value_tests(before,after,index,path):
    if index.get('base_exit_code')!=0 or not index.get('comparison_values_complete'):return 0
    changes=[]
    def same(a,b):
        if type(a) is not type(b):return False
        if isinstance(a,ast.Compare) and len(a.ops)==len(b.ops)==1:
            old_op,new_op=type(a.ops[0]).__name__,type(b.ops[0]).__name__
            if ast.dump(a)==ast.dump(b):return True
            if old_op not in OPERATORS or new_op not in OPERATORS:return False
            replacements=[]
            for old,new in ((a.left,b.left),(a.comparators[0],b.comparators[0])):
                if ast.dump(old)==ast.dump(new):replacements.append(None)
                else:
                    try:old_value,new_value=pack(ast.literal_eval(old)),pack(ast.literal_eval(new))
                    except (ValueError,TypeError,SyntaxError,RecursionError):return False
                    if old_value is None or new_value is None:return False
                    replacements.append(new_value)
            changes.append((f'{path}:{a.lineno}:{a.col_offset}',old_op,new_op,replacements))
            return True
        if isinstance(a,ast.AST):return all(same(getattr(a,key),getattr(b,key)) for key in a._fields)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        return a==b
    if not same(before,after) or not changes:return 0
    result=(1<<len(index['tests']))-1
    locations=index.get('comparison_value_locations',())
    for location,old_op,new_op,replacements in changes:
        if location not in locations:return 0
        unsafe=int(index.get('comparison_value_unknown',{}).get(location,'0'),16)
        for encoded,value in index.get('comparison_values',{}).get(location,{}).items():
            op,left,right,old_result=json.loads(encoded)
            try:
                a,b=unpack(replacements[0] or left),unpack(replacements[1] or right)
                new_result=OPERATORS[new_op](a,b)
                safe=op==old_op and type(new_result) is bool and new_result==old_result
            except (ValueError,TypeError,OverflowError):safe=False
            if not safe:unsafe|=int(value,16)
        result&=~unsafe
    return result
