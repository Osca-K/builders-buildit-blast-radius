import ast
import json
import unittest
import primitive_comparisons as trace
from comparison_value_equivalence import equivalent_value_tests


class ComparisonValues(unittest.TestCase):
    def setUp(self):
        trace.observations.clear();trace.unknown.clear();trace.locations.clear()
        trace.install(lambda:'test:a')

    def index(self,pairs,unknown='0'):
        return {'tests':['a','b','c'],'base_exit_code':0,'comparison_values_complete':True,
                'comparison_value_locations':['x.py:1:0'],
                'comparison_values':{'x.py:1:0':{json.dumps([op,trace.pack(a),trace.pack(b),result],separators=(',',':')):mask
                    for op,a,b,result,mask in pairs}},'comparison_value_unknown':{'x.py:1:0':unknown}}

    def prove(self,before,after,index):
        return equivalent_value_tests(ast.parse(before),ast.parse(after),index,'x.py')

    def test_boundary_operator_retains_every_affected_test(self):
        index=self.index([('Lt',1,2,True,'1'),('Lt',2,2,False,'2')])
        self.assertEqual(self.prove('value < 2','value <= 2',index),5)
        index['comparison_value_unknown']['x.py:1:0']='4'
        self.assertEqual(self.prove('value < 2','value <= 2',index),1)

    def test_literal_operand_change_uses_observed_other_operand(self):
        index=self.index([('Lt',1,2,True,'1'),('Lt',2,2,False,'2')])
        self.assertEqual(self.prove('value < 2','value < 3',index),5)
        self.assertEqual(self.prove('value < 2','changed(value) < 3',index),0)

    def test_all_observations_must_be_neutral_for_a_test(self):
        index=self.index([('Lt',1,2,True,'1'),('Lt',2,2,False,'1')])
        self.assertEqual(self.prove('value < 2','value <= 2',index),6)

    def test_tuple_versions_and_string_literals_are_lossless(self):
        index=self.index([('Lt',(23,11),(23,12),True,'1'),('Lt',(23,12),(23,12),False,'2')])
        self.assertEqual(self.prove('version < (23,12)','version <= (23,12)',index),5)
        for value in (None,True,-4,1.5,'\u2603',b'\x00\xff',(1,'a',(None,False))):
            self.assertEqual(trace.unpack(trace.pack(value)),value)

    def test_missing_or_incomplete_trace_disables_proof(self):
        index=self.index([('Lt',1,2,True,'1')])
        index['comparison_values_complete']=False
        self.assertEqual(self.prove('value < 2','value <= 2',index),0)
        index['comparison_values_complete']=True;index['comparison_value_locations']=[]
        self.assertEqual(self.prove('value < 2','value <= 2',index),0)

    def test_noncomparison_or_mixed_edits_are_not_pruned(self):
        index=self.index([('Lt',1,2,True,'1')])
        self.assertEqual(self.prove('value < 2\nother=1','value <= 2\nother=2',index),0)
        self.assertEqual(self.prove('value < 2 < 4','value <= 2 < 4',index),0)

    def test_unknown_values_exceptions_and_overflow_are_recorded(self):
        class Custom:
            def __eq__(self,other):return True
        self.assertTrue(trace.compare('custom','Eq',Custom(),None))
        self.assertIn('test:a',trace.unknown['custom'])
        with self.assertRaises(TypeError):trace.compare('bad','Lt',1,'a')
        self.assertIn('test:a',trace.unknown['bad'])
        for value in range(trace.MAX_PAIRS+1):trace.compare('limit','Lt',value,500)
        self.assertIn('test:a',trace.unknown['limit'])
        self.assertEqual(len(trace.observations['limit']),trace.MAX_PAIRS)

    def test_nonfinite_large_or_mutable_values_remain_unknown(self):
        for value in (float('nan'),float('inf'),1<<80,'x'*65,[1,2],{'a':1},(1,[2])):
            self.assertIsNone(trace.pack(value))


if __name__=='__main__':unittest.main()
