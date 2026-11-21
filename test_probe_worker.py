import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProbeCompletion(unittest.TestCase):
    def run_probe(self,source,tests,bad_collection=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tests').mkdir()
            (root/'tests/test_cases.py').write_text(source,encoding='utf-8')
            if bad_collection:(root/'tests/test_broken.py').write_text('def broken(:\n')
            request=root/'request.json';report=root/'report.json'
            request.write_text(json.dumps({'tests':tests}))
            run=subprocess.run([sys.executable,str(Path(__file__).with_name('probe_worker.py')),str(request),str(report)],
                               cwd=root,env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'),capture_output=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr.decode())
            return json.loads(report.read_text())

    def test_every_failed_subtest_and_setup_error_is_retained(self):
        source='''import unittest
class TestCases(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(1, 1)
    def test_subfail(self):
        for x in (1, 2):
            with self.subTest(x=x):
                self.assertEqual(x, 1)
class TestSetup(unittest.TestCase):
    def setUp(self):
        raise RuntimeError("setup failure")
    def test_setup(self):
        pass
'''
        tests=['tests/test_cases.py::TestCases::test_ok','tests/test_cases.py::TestCases::test_subfail',
               'tests/test_cases.py::TestSetup::test_setup']
        result=self.run_probe(source,tests)
        self.assertTrue(result['complete'],result)
        self.assertEqual(set(result['failed']),set(tests[1:]))

    def test_missing_test_and_collection_failure_cannot_prune(self):
        source='def test_ok():\n    assert True\n'
        missing=self.run_probe(source,['tests/test_cases.py::test_missing'])
        self.assertFalse(missing['complete'])
        broken=self.run_probe(source,['tests/test_cases.py::test_ok'],bad_collection=True)
        self.assertTrue(broken['collection_failed'])
        self.assertFalse(broken['complete'])


if __name__=='__main__':unittest.main()
