"""Optional bounded execution of incoming patches, with conservative fallback."""
import ast
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time


class Probes:
    def __init__(self):
        self.started=time.monotonic()
        self.root=Path('/tmp/rwx-probe')
        self.prepared=False
        self.cpu_limit=float(os.environ.get('PROBE_CPU_LIMIT','45'))
        self.wall_limit=float(os.environ.get('PROBE_WALL_LIMIT','100'))
        self.mode=os.environ.get('PROBE_MODE','off')
        self.log=[]

    @staticmethod
    def cpu():
        own=resource.getrusage(resource.RUSAGE_SELF)
        children=resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime

    def enabled(self):
        return self.mode!='off' and self.cpu()<self.cpu_limit and time.monotonic()-self.started<self.wall_limit

    def prepare(self):
        if not self.prepared:
            shutil.copytree('/opt/sqlglot',self.root,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache'))
            self.prepared=True

    def filter(self,index,text,selected):
        if not selected or not self.enabled():return selected
        from selector import diff,patched,source_tree,changed_class_constants
        try:
            changes=diff(text)
            replacements={}
            literal_only=True
            for change in changes:
                path=change['old']
                if path!=change['new'] or not path or not path.startswith('sqlglot/') or not path.endswith('.py'):
                    return selected
                relative=Path(path)
                if relative.is_absolute() or '..' in relative.parts:return selected
                before=index['sources'].get(path)
                if before is None:return selected
                after=patched(before,change)
                tree=ast.parse(after)
                literal_only=literal_only and bool(changed_class_constants(source_tree(before),tree))
                replacements[path]=after
            total=sum(test['ms'] for test in selected)
            longest=max(test['ms'] for test in selected)
            if self.mode=='cheap':
                if not literal_only or len(selected)<2 or total>1500:return selected
                targets=selected
                timeout=8
            elif self.mode=='long':
                if longest<3000 or len(selected)<2:return selected
                targets=[max(selected,key=lambda test:test['ms'])]
                timeout=min(45,max(8,longest/1000*1.5))
            else:
                if literal_only and len(selected)>=2 and total<=1500:
                    targets=selected;timeout=8
                elif longest>=3000 and len(selected)>=2:
                    targets=[max(selected,key=lambda test:test['ms'])]
                    timeout=min(45,max(8,longest/1000*1.5))
                else:return selected
            remaining=self.wall_limit-(time.monotonic()-self.started)
            if remaining<timeout:return selected
            self.prepare()
            restored={}
            started_cpu=self.cpu();started=time.monotonic()
            result={'complete':False}
            try:
                for path,after in replacements.items():
                    target=self.root/path
                    restored[target]=target.read_bytes()
                    target.write_text(after,encoding='utf-8')
                request=Path('/tmp/rwx-request.json');report=Path('/tmp/rwx-report.json')
                request.write_text(json.dumps({'tests':[test['id'] for test in targets]}))
                if report.exists():report.unlink()
                env=dict(os.environ,PYTHONPATH=str(self.root),PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',SKIP_INTEGRATION='0',HOME='/tmp')
                process=subprocess.Popen([sys.executable,'/app/probe_worker.py',str(request),str(report)],cwd=self.root,env=env,
                                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                try:process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                if process.returncode==0 and report.exists():result=json.loads(report.read_text())
            finally:
                for target,before in restored.items():target.write_bytes(before)
            kept=selected
            if result.get('complete'):
                passed={test['id'] for test in targets}-set(result['failed'])
                kept=[test for test in selected if test['id'] not in passed]
            self.log.append({'targets':len(targets),'selected':len(selected),'remaining':len(kept),
                             'complete':result.get('complete',False),'cpu':self.cpu()-started_cpu,
                             'wall':time.monotonic()-started,'longest_ms':longest})
            return kept
        except (ValueError,TypeError,KeyError,OSError,SyntaxError,subprocess.SubprocessError):
            return selected

    def finish(self):
        print('RUNTIME_PROBES='+json.dumps(self.log,separators=(',',':')),file=sys.stderr)
