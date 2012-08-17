'''
'''

import re
from datetime import datetime

from validator import SchemaValidator, SchemaError
from extended import ExtendedSchemaValidator


class SchemaCoercer(SchemaValidator):
    ''' A validator that will try to bend types when the provided ones aren't
        really what we expected.
    '''

    def validate_type(self, x, fieldname, schema, fieldtype=None):
        self.push_error_stack()
        super(SchemaCoercer, self).validate_type(x, fieldname, schema, fieldtype)
        errs = self.pop_error_stack()
        if errs:
            if not fieldtype or not fieldname in x:
                self._error('impossible-coercion', fieldtype)
                return

            # Whatever happened, the expected type was not the one intended, so
            # we're going to try and see if we can coerce the original value
            # to the desired type.
            coerce_method = getattr(self, 'coerce_' + fieldtype) if isinstance(fieldtype, (str, unicode)) else None
            if coerce_method:
                self.push_error_stack()
                coerce_method(x, fieldname, schema)
                errs = self.pop_error_stack()

                if not errs:
                    super(SchemaCoercer, self).validate_type(x, fieldname, schema, fieldtype)
                else:
                    self.error_list += errs
            else:
                self._error('impossible-coercion', fieldtype)

    def coerce_integer(self, x, fieldname, schema):
        value = self.get(x, fieldname)
        try:
            value = int(value)
        except:
            try:
                value = int(re.match(r'-?\s*\d+', value).group(0))
            except:
                self._error('impossible-integer-coercion', value)
        x[fieldname] = value

    def coerce_number(self, x, fieldname, schema):
        value = self.get(x, fieldname)
        try:
            value = float(re.match(r'-?\s*\d+(\.\d+)?', value).group(0))
        except:
            self._error('impossible-number-coercion', value)
        x[fieldname] = value

    def coerce_datetime(self, x, fieldname, schema):
        value = self.get(x, fieldname)
        for format in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%SZ']:
            try:
                x[fieldname] = datetime.strptime(value, format)
                return
            except:
                pass
        self._error('impossible-datetime-coercion', value)

    def coerce_string(self, x, fieldname, schema):
        value = self.get(x, fieldname)
        try:
            x[fieldname] = unicode(value)
        except:
            self._error('impossible-string-coercion', value)

    def coerce_object(self, x, fieldname, schema):
        self._error('impossible-object-coercion', self.get(x, fieldname))

    def coerce_array(self, x, fieldname, schema):
        x[fieldname] = [self.get(x, fieldname)]

    def coerce_boolean(self, x, fieldname, schema):
        newvalue = True if self.get(x, fieldname) else False
        x[fieldname] = newvalue

    def validate_additionalProperties(self, x, fieldname, schema, additionalProperties=None):
        '''
        Remove additional properties of a JSON object that were not
        specifically defined by the properties property OR the patternProperties
        object.
        '''
        # Shouldn't be validating additionalProperties on non-dicts
        value = self.get(x, fieldname)
        if not isinstance(value, dict):
            return

        # If additionalProperties is the boolean value True then we accept
        # any additional properties.
        if isinstance(additionalProperties, bool) and additionalProperties:
            return

        value = self.get(x, fieldname)
        if isinstance(additionalProperties, (dict, bool)):
            properties = schema.get("properties", [])
            patternProperties = schema.get('patternProperties', [])
            if properties is None:
                properties = {}
            if value is None:
                value = {}

            props_to_delete = []

            for eachProperty in value:
                if eachProperty in properties:
                    continue

                # Check if the property matches a patternProperty
                matched = False
                for pattern in patternProperties:
                    if re.match(pattern, eachProperty):
                        matched = True
                        break
                if matched:
                    continue

                # If additionalProperties is the boolean value False
                # then we don't accept any additional properties.
                if (isinstance(additionalProperties, bool) and not additionalProperties):
                    props_to_delete.append(eachProperty)
                else:
                    # If it's an object, then we try to validate the value
                    # on the schema.
                    self.__validate(eachProperty, value, additionalProperties)

            # When coercing, we delete the incriminated property
            for prop in props_to_delete:
                del value[prop]
        else:
            raise SchemaError("additionalProperties schema definition for "
                              "field '%s' is not an object" % fieldname)


class ExtendedSchemaCoercer(SchemaCoercer, ExtendedSchemaValidator):
    pass
