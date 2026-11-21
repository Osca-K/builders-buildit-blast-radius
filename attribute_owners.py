"""Expand receiver coverage to possible declaration modules on pristine classes."""
import importlib
import inspect

def expand(index):
    attributes=index.get('attributes',{})
    merged={key:int(value,16) for key,value in attributes.items()}
    modules={}
    def module_classes(path):
        if path in modules:return modules[path]
        name=path[:-3].replace('/','.')
        if name.endswith('.__init__'):name=name[:-9]
        module=importlib.import_module(name)
        found=[];seen=set()
        def walk(namespace):
            for value in list(namespace.values()):
                if inspect.isclass(value) and id(value) not in seen and value.__module__==name:
                    seen.add(id(value));found.append(value);walk(vars(value))
        walk(vars(module));modules[path]=found
        return found
    for key,mask in list(merged.items()):
        path,attribute=key.rsplit(':',1)
        for cls in module_classes(path):
            for owner in cls.__mro__:
                if attribute in vars(owner):
                    owner_path=owner.__module__.replace('.','/')+'.py'
                    if owner_path not in index['sources']:
                        owner_path=owner.__module__.replace('.','/')+'/__init__.py'
                    if owner_path in index['sources']:
                        target=owner_path+':'+attribute
                        merged[target]=merged.get(target,0)|mask
                    break
    index['attributes']={key:format(mask,'x') for key,mask in merged.items()}
    index['attribute_declarations']=True
    return index

if __name__=='__main__':
    import gzip,json,sys
    with gzip.open(sys.argv[1],'rt',encoding='utf-8') as stream:index=json.load(stream)
    expand(index)
    with gzip.open(sys.argv[2],'wt',encoding='utf-8') as stream:json.dump(index,stream,separators=(',',':'))
