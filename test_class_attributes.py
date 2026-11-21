import ast
import unittest
import class_attributes
from comparison_types import Rewrite


class SchemaTracing(unittest.TestCase):
    def setUp(self):
        class_attributes.observations.clear()
        class_attributes._owners.clear()
        class_attributes.install(lambda:'test:reader')

    def test_inherited_and_derived_reads_reach_schema_declaration(self):
        base=type('Base',(),{'__module__':'sqlglot.expressions.example','arg_types':{'x':True}})
        child=type('Child',(base,),{'required_args':{'x'}})
        self.assertEqual(class_attributes.read(child,'required_args'),{'x'})
        self.assertEqual(class_attributes.read(child(),'arg_types'),{'x':True})
        self.assertEqual(class_attributes.observations,
                         {'sqlglot/expressions/example.py:Base:arg_types':{'test:reader'}})

    def test_import_reads_are_conservative_and_derivation_is_special(self):
        base=type('Base',(),{'__module__':'sqlglot.expressions.example','arg_types':{'x':True}})
        class_attributes.install(lambda:'')
        class_attributes.read(base,'arg_types',derived=True)
        self.assertEqual(class_attributes.observations,{})
        class_attributes.read(base,'arg_types')
        self.assertEqual(next(iter(class_attributes.observations.values())),{'unscoped'})

    def test_rewrite_preserves_attribute_values_and_assignment_targets(self):
        base=type('Base',(),{'__module__':'sqlglot.expressions.example','arg_types':{'x':True}})
        tree=Rewrite('sqlglot/example.py').visit(ast.parse('result = obj.arg_types\nobj.required_args = {"x"}\n'))
        namespace={'obj':base,'_rwx_schema_read':class_attributes.read}
        exec(compile(ast.fix_missing_locations(tree),'<schema-test>','exec'),namespace)
        self.assertIs(namespace['result'],base.arg_types)
        self.assertEqual(base.required_args,{'x'})


if __name__=='__main__':unittest.main()
