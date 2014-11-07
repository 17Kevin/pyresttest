import unittest
import validators
from binding import Context


class ValidatorsTest(unittest.TestCase):
    """ Testing for validators and extract functions """

    def test_dict_query(self):
        """ Test actual query logic """
        mydict = {'key': {'val': 3}}
        query = 'key.val'
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(3, val)

        array = [1,2,3]
        mydict = {'key': {'val': array}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(array, val)

        mydict = {'key': {'v': 'pi'}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(None, val)

        # Array test
        query = 'key.val.1'
        mydict = {'key': {'val': array}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(array[1], val)

        # Templating test
        query = 'key.$node'
        mydict = {'key': {'val': 3}}
        context = Context()
        context.bind_variable('node', 'val')
        val = validators.query_dictionary(query, mydict, context=context, isTemplate=True)
        self.assertEqual(3, val)

        # Error cases
        query = 'key.val.5'
        mydict = {'key': {'val': array}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(None, val)

        query = 'key.val.pi'
        mydict = {'key': {'val': array}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(None, val)

        # Return the first object?
        query = 'key.0'
        mydict = {'key': {'val': array}}
        val = validators.query_dictionary(query, mydict)
        self.assertEqual(None, val)

    def test_parse_extractor_minijson(self):
        config = 'key.val'
        extract_fn = validators.parse_extractor_minijson(config)
        myjson = '{"key": {"val": 3}}'
        context = Context()
        context.bind_variable('node', 'val')

        extracted = extract_fn(myjson)
        self.assertEqual(3, extracted)
        self.assertEqual(extracted, extract_fn(myjson, context))

        try:
            val = extract_fn('[31{]')
            self.fail("Should throw exception on invalid JSON")
        except ValueError:
            pass

        # Templating
        config = {'template': 'key.$node'}
        extract_fn = validators.parse_extractor_minijson(config)
        self.assertEqual(3, extract_fn(myjson, context=context))

    def test_get_extract_fn(self):
        config = {
            'jsonpath_mini': 'key.val',
            'comparator': 'eq',
            'expected': 3
        }
        extractor = validators._get_extract_fn(config)
        myjson = '{"key": {"val": 3}}'
        extracted = extractor.extract(myjson)
        self.assertEqual(3, extracted)

    def test_validator_compare_basic(self):
        """ Basic tests of the comparison validators, and templating"""
        config = {
            'jsonpath_mini': 'key.val',
            'comparator': 'eq',
            'expected': 3
        }
        comp_validator = validators.ComparatorValidator.parse(config)
        myjson_pass = '{"id": 3, "key": {"val": 3}}'
        myjson_fail = '{"id": 3, "key": {"val": 4}}'

        self.assertTrue(comp_validator.validate(myjson_pass))
        self.assertFalse(comp_validator.validate(myjson_fail))

    def test_validator_comparator_templating(self):
        """ Try templating comparator validator """
        config = {
            'jsonpath_mini': {'template': 'key.$node'},
            'comparator': 'eq',
            'expected': 3
        }
        context = Context()
        context.bind_variable('node', 'val')
        myjson_pass = '{"id": 3, "key": {"val": 3}}'
        myjson_fail = '{"id": 3, "key": {"val": 4}}'
        comp = validators.ComparatorValidator.parse(config)

        self.assertTrue(comp.validate(myjson_pass, context=context))
        self.assertFalse(comp.validate(myjson_fail, context=context))

        # Template expected
        config['expected'] = {'template' : '$id'}
        context.bind_variable('id', 3)
        self.assertTrue(comp.validate(myjson_pass, context=context))
        self.assertFalse(comp.validate(myjson_fail, context=context))

    def test_validator_comparator_extract(self):
        """ Try comparing two extract expressions """
        config = {
            'jsonpath_mini': 'key.val',
            'comparator': 'eq',
            'expected': {'jsonpath_mini': 'id'}
        }
        myjson_pass = '{"id": 3, "key": {"val": 3}}'
        myjson_fail = '{"id": 3, "key": {"val": 4}}'
        comp = validators.ComparatorValidator.parse(config)
        self.assertTrue(comp.validate(myjson_pass))
        self.assertFalse(comp.validate(myjson_fail))

if __name__ == '__main__':
    unittest.main()