'''
'''

from datetime import datetime

from validator import SchemaValidator


class ExtendedSchemaValidator(SchemaValidator):
    '''
        A JSON schema validator, with support for the date type, and a few other
        validators either present in the JSON Schema specifications but not in
        validictory, or needed for custom use.

        To add a new type or a new attribute is fairly easy ; just add the corresponding
        validate_type_<typename> or validate_<attribute> to this class.
    '''

    def validate_type_datetime(self, val):
        ''' This function is added to Validictory, since BSON allows us
            to specify dates.
        '''
        return isinstance(val, datetime)

    def validate_minProperties(self, x, fieldname, schema, min_properties=None):
        ''' Validate that the object has at least `min_properties` properties.
        '''
        value = self.get(x, fieldname)
        if isinstance(value, dict) and len(value) < min_properties:
            self._error('not-enough-properties')

    def validate_maxProperties(self, x, fieldname, schema, max_properties=None):
        ''' Validate that the object has at most `max_properties` properties.
        '''
        value = self.get(x, fieldname)
        if isinstance(value, dict) and len(value) < max_properties:
            self._error('too-many-properties')

    def validate_requireEither(self, x, fieldname, schema, one_of=None):
        if not fieldname in x:
            # We can't check this property in an inexistant field.
            return

        for prop in one_of:
            self.push_error_stack()
            self.validate_required(self.get(x, fieldname), prop, schema, True)
            errs = self.pop_error_stack()
            if not errs:
                return
        self._error('none-of-required', one_of)
