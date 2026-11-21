import ast
import pickle
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
        namespace={'_rwx_dict':reads.track}
        exec(compile(ast.fix_missing_locations(tree),'<dictionary-test>','exec'),namespace)
        self.assertEqual(reads.origins,{'sqlglot/test.py:A.B:FLAGS'})
        self.assertEqual(namespace['A'].B.FLAGS['a'],(1,2))


if __name__=='__main__':unittest.main()
