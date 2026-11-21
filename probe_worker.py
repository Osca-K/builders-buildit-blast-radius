"""Ephemeral pytest probe; never reads or stores mutation answer labels."""
import json
from pathlib import Path
import sys
import pytest


class ProbeReports:
    def __init__(self,expected):
        self.expected=set(expected)
        self.collected=set()
        self.completed=set()
        self.failed=set()
        self.collection_failed=False
        self.unexpected=False

    def pytest_collection_modifyitems(self,session,config,items):
        chosen=[];deselected=[]
        for item in items:
            if item.nodeid in self.expected:chosen.append(item)
            else:deselected.append(item)
        self.collected={item.nodeid for item in chosen}
        items[:]=chosen
        config.hook.pytest_deselected(items=deselected)

    def pytest_collectreport(self,report):
        if report.failed:self.collection_failed=True

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_logreport(self,report):
        if report.nodeid not in self.expected:self.unexpected=True
        if report.failed:self.failed.add(report.nodeid)
        if report.when=='teardown':self.completed.add(report.nodeid)

    def result(self,code):
        complete=(int(code) in (0,1) and self.collected==self.expected
                  and self.completed==self.expected and not self.collection_failed
                  and not self.unexpected)
        return {'complete':complete,'failed':sorted(self.failed),'completed':len(self.completed),
                'expected':len(self.expected),'exit_code':int(code),'collection_failed':self.collection_failed}


def main():
    request=json.loads(Path(sys.argv[1]).read_text())
    plugin=ProbeReports(request['tests'])
    code=pytest.main(['tests','-p','no:terminal','-p','no:cacheprovider','-p','no:logging'],plugins=[plugin])
    Path(sys.argv[2]).write_text(json.dumps(plugin.result(code)),encoding='utf-8')


if __name__=='__main__':main()
