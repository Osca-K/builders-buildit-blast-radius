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

    def test_negative_and_container_literals_select_readers(self):
        for value in ('-2', '{"x": (16, 2), "y": [1, 3]}', '{1, 2}', '[]'):
            self.assertEqual(self.select(SOURCE.replace('True', value)), 1)

    def test_invalid_literal_container_keeps_all_users(self):
        self.assertEqual(self.select(SOURCE.replace('True', '{[]: 1}')), 3)

    def test_container_expression_with_call_keeps_all_users(self):
        self.assertEqual(self.select(SOURCE.replace('True', '{"x": unsafe()}')), 3)

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

    def test_expression_schema_uses_exact_declaring_class(self):
        source='class A:\n    arg_types = {"x": True}\nclass B:\n    arg_types = {"y": True}\n'
        changed=source.replace('"x": True','"x": False')
        index=self.index()
        index['sources']={'dialect.py':source}
        index['class_attribute_complete']=True
        index['class_schema_paths']=['dialect.py']
        index['class_attributes']={'dialect.py:A:arg_types':'1','dialect.py:B:arg_types':'2'}
        patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
                                         fromfile='a/dialect.py',tofile='b/dialect.py'))
        self.assertEqual(choose(index,patch),1)
        index['class_attributes']={}
        self.assertEqual(choose(index,patch),0)
        index['class_attribute_complete']=False
        self.assertEqual(choose(index,patch),3)

    def test_expression_schema_mixed_method_edit_keeps_file_users(self):
        source=SOURCE.replace('FLAG = True','arg_types = {"x": True}')
        changed=source.replace('"x": True','"x": False').replace('return 1','return 2')
        index=self.index()
        index['sources']={'dialect.py':source}
        index['class_attribute_complete']=True
        index['class_schema_paths']=['dialect.py']
        index['class_attributes']={'dialect.py:Dialect:arg_types':'1'}
        patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
                                         fromfile='a/dialect.py',tofile='b/dialect.py'))
        self.assertEqual(choose(index,patch),3)

    def test_expression_invalid_schema_keeps_importers(self):
        source=SOURCE.replace('FLAG = True','arg_types = {"x": True}')
        for value in ('1','[]','None','{"x": []}'):
            changed=source.replace('{"x": True}',value)
            index=self.index()
            index['sources']={'dialect.py':source}
            index['class_attribute_complete']=True
            index['class_schema_paths']=['dialect.py']
            index['class_attributes']={}
            patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
                                             fromfile='a/dialect.py',tofile='b/dialect.py'))
            self.assertEqual(choose(index,patch),3)

    def test_dictionary_value_change_selects_key_readers_and_bulk_readers(self):
        source=SOURCE.replace('FLAG = True','FLAG = {"a": (1, 2), "b": 3}')
        changed=source.replace('(1, 2)','(2, 2)')
        index=self.index()
        index['sources']={'dialect.py':source}
        index['dictionary_reads_complete']=True
        index['dictionary_origins']=['dialect.py:Dialect:FLAG']
        index['dictionary_reads']={'dialect.py:Dialect:FLAG':{'key:"a"':'1','key:"b"':'2'}}
        patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
                                         fromfile='a/dialect.py',tofile='b/dialect.py'))
        self.assertEqual(choose(index,patch),1)
        index['dictionary_reads']['dialect.py:Dialect:FLAG']['*']='2'
        self.assertEqual(choose(index,patch),3)
        index['dictionary_reads']={}
        self.assertEqual(choose(index,patch),0)

    def test_dictionary_reorder_or_new_key_retains_attribute_fallback(self):
        source=SOURCE.replace('FLAG = True','FLAG = {"a": 1, "b": 2}')
        index=self.index()
        index['sources']={'dialect.py':source}
        index['dictionary_reads_complete']=True
        index['dictionary_origins']=['dialect.py:Dialect:FLAG']
        index['dictionary_reads']={}
        for value in ('{"b": 3, "a": 1}','{"a": 3, "c": 2}'):
            changed=source.replace('{"a": 1, "b": 2}',value)
            patch=''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),
                                             fromfile='a/dialect.py',tofile='b/dialect.py'))
            self.assertEqual(choose(index,patch),1)

if __name__ == '__main__':
    unittest.main()
