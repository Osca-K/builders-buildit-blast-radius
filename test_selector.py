"""Regression checks for conservative selection across mixed edits."""
import difflib
import unittest
import sys
import types
from selector import choose, diff
from attribute_owners import expand

SOURCE = 'class Dialect:\n    FLAG = True\n\n    def parse(self):\n        return 1\n'

class SelectionSafety(unittest.TestCase):
    def index(self):
        return {'tests': ['constant_reader', 'method_reader'],
                'sources': {'dialect.py': SOURCE}, 'owners': {},
                'lines': {'dialect.py': {'2': '3', '4': '2', '5': '2'}},
                'files': {'dialect.py': '3'},
                'attributes': {'dialect.py:FLAG': '1'},
                'attribute_declarations': True}

    def select(self, changed, index=None):
        patch = ''.join(difflib.unified_diff(SOURCE.splitlines(True), changed.splitlines(True),
                                            fromfile='a/dialect.py', tofile='b/dialect.py'))
        return choose(index or self.index(), patch)

    def test_scalar_flag_can_select_observed_readers(self):
        self.assertEqual(self.select(SOURCE.replace('True', 'False')), 1)

    def test_mixed_flag_and_method_edit_keeps_both(self):
        self.assertEqual(self.select(SOURCE.replace('True', 'False').replace('return 1', 'return 2')), 3)

    def test_new_import_side_effect_keeps_file_users(self):
        self.assertEqual(self.select(SOURCE.replace('True', 'unknown_function()')), 3)

    def test_legacy_receiver_only_index_cannot_prune_declaration(self):
        index = self.index()
        del index['attribute_declarations']
        self.assertEqual(self.select(SOURCE.replace('True', 'False'), index), 3)

    def test_syntax_error_keeps_all_tests(self):
        self.assertEqual(self.select(SOURCE.replace('True', '(')), 3)

    def test_method_change_keeps_method_reader(self):
        self.assertEqual(self.select(SOURCE.replace('return 1', 'return 2')), 2)

    def test_replacement_does_not_touch_next_function(self):
        patch='--- a/x.py\n+++ b/x.py\n@@ -2,1 +2,1 @@\n-    return 1\n+    return 2\n'
        self.assertEqual(diff(patch)[0]['lines'], {2})

    def test_pure_insertion_keeps_both_neighbors(self):
        patch='--- a/x.py\n+++ b/x.py\n@@ -2,0 +3,1 @@\n+    work()\n'
        self.assertEqual(diff(patch)[0]['lines'], {2,3})

    def test_inherited_attribute_reaches_declaration_module(self):
        base_module=types.ModuleType('_coverage_base')
        child_module=types.ModuleType('_coverage_child')
        base=type('Base',(),{'__module__':base_module.__name__,'FLAG':True})
        child=type('Child',(base,),{'__module__':child_module.__name__})
        base_module.Base=base;child_module.Child=child
        sys.modules[base_module.__name__]=base_module
        sys.modules[child_module.__name__]=child_module
        try:
            index={'sources':{'_coverage_base.py':'','_coverage_child.py':''},
                   'attributes':{'_coverage_child.py:FLAG':'2'}}
            expand(index)
            self.assertEqual(index['attributes']['_coverage_base.py:FLAG'],'2')
        finally:
            del sys.modules[base_module.__name__],sys.modules[child_module.__name__]

if __name__ == '__main__':
    unittest.main()
