import ast
import pickle
import json
import unittest
import dictionary_reads as reads
from comparison_types import Rewrite


class DictionaryTracing(unittest.TestCase):
    def setUp(self):
        reads.observations.clear();reads.origins.clear()
        reads.install(lambda:'test:reader')

    def test_key_reads_and_presence_are_distinct(self):
        value=reads.track({'a':(1,2),'b':3},'origin')
        self.assertIn('a',value)
        self.assertTrue(value)
        self.assertEqual(list(value),['a','b'])
        self.assertEqual(reads.observations,{})
        self.assertEqual(value.get('a'),(1,2))
        self.assertEqual(set(reads.observations['origin']),{'key:"a"'})

    def test_copies_preserve_value_dependencies(self):
        value=reads.track({'a':1,'b':2},'origin')
        copied=value.copy()
        reads.observations.clear()
        self.assertEqual(copied['b'],2)
        self.assertEqual(set(reads.observations['origin']),{'key:"b"'})
        reads.observations.clear()
        self.assertEqual(dict(value),{'a':1,'b':2})
        self.assertEqual(set(reads.observations['origin']),{'key:"a"','key:"b"'})

    def test_bulk_and_serialized_values_are_wildcard_dependencies(self):
        value=reads.track({'a':1,'b':2},'origin')
        for operation in (lambda:list(value.items()),lambda:list(value.values()),
                          lambda:value=={'a':1,'b':2},lambda:repr(value),
                          lambda:pickle.dumps(value),lambda:value|{'c':3}):
            reads.observations.clear();operation()
            self.assertIn('*',reads.observations['origin'])

    def test_rewrite_tracks_nested_class_literal_dictionary(self):
        tree=Rewrite('sqlglot/test.py').visit(ast.parse('class A:\n    class B:\n        FLAGS = {"a": (1, 2)}\n'))
        namespace={'_rwx_dict':reads.track,'_rwx_guard_call':reads.call}
        exec(compile(ast.fix_missing_locations(tree),'<dictionary-test>','exec'),namespace)
        self.assertEqual(reads.origins,{'sqlglot/test.py:A.B:FLAGS'})
        self.assertEqual(namespace['A'].B.FLAGS['a'],(1,2))

    def test_mapping_expansion_keeps_read_dependencies(self):
        value=reads.track({'a':1,'b':2},'origin')
        self.assertEqual({**value},{'a':1,'b':2})
        self.assertEqual(set(reads.observations['origin']),{'key:"a"','key:"b"'})
        reads.observations.clear()
        def consume(**kwargs):return kwargs
        self.assertEqual(consume(**value),{'a':1,'b':2})
        self.assertEqual(set(reads.observations['origin']),{'key:"a"','key:"b"'})

    def test_explicit_dict_base_calls_and_json_are_observed(self):
        value=reads.track({'a':1,'b':2},'origin')
        tree=Rewrite('sqlglot/test.py').visit(ast.parse('result = dict.__getitem__(value,"a")\n'))
        namespace={'value':value,'_rwx_dict_method':reads.base_method,'_rwx_guard_call':reads.call}
        exec(compile(ast.fix_missing_locations(tree),'<dictionary-test>','exec'),namespace)
        self.assertEqual(namespace['result'],1)
        self.assertIn('*',reads.observations['origin'])
        for operation in (lambda:json.dumps({'nested':[value]}),
                          lambda:json.JSONEncoder().encode(value),
                          lambda:list(json.JSONEncoder().iterencode(value))):
            reads.observations.clear();operation()
            self.assertIn('*',reads.observations['origin'])

    def test_unknown_consumers_mark_wildcard_and_length_keeps_presence_only(self):
        value=reads.track({'a':1},'origin')
        self.assertEqual(reads.call(len,value),1)
        self.assertEqual(reads.observations,{})
        def external(mapping):return dict.__getitem__(mapping,'a')
        self.assertEqual(reads.call(external,value),1)
        self.assertIn('*',reads.observations['origin'])


if __name__=='__main__':unittest.main()
