import re
import sys
import copy
import socket
from functools import wraps

from datetime import datetime
import warnings
from collections import Mapping, Container

if sys.version_info[0] == 3:
    _str_type = str
    _int_types = (int,)
else:
    _str_type = basestring
    _int_types = (int, long)


class SchemaError(ValueError):
    """
    errors encountered in processing a schema (subclass of :class:`ValueError`)
    """


class ValidationError(ValueError):
    """
    validation errors encountered during validation (subclass of
    :class:`ValueError`)
    """


def _generate_datetime_validator(format_option, dateformat_string):
    def validate_format_datetime(validator, fieldname, value, format_option):
        try:
            datetime.strptime(value, dateformat_string)
        except ValueError:
            validator.error_list.append(
                "Value %(value)r of field '%(fieldname)s' is not in "
                "'%(format_option)s' format" % locals())

    return validate_format_datetime

validate_format_date_time = _generate_datetime_validator('date-time',
                                                         '%Y-%m-%dT%H:%M:%SZ')
validate_format_date = _generate_datetime_validator('date', '%Y-%m-%d')
validate_format_time = _generate_datetime_validator('time', '%H:%M:%S')


def validate_format_utc_millisec(validator, fieldname, value, format_option):
    if not isinstance(value, (int, float)):
        validator.error_list.append("Value %(value)r of field '%(fieldname)s' is "
                              "not a number" % locals())

    if not value > 0:
        validator.error_list.append("Value %(value)r of field '%(fieldname)s' is "
                              "not a positive number" % locals())


def validate_format_ip_address(validator, fieldname, value, format_option):
    try:
        socket.inet_aton(value)
        # Make sure we expect "X.X.X.X" as socket.inet_aton() converts "1"
        # to "0.0.0.1"
        ip = len(value.split('.')) == 4
    except:
        ip = False
    if not ip:
        validator.error_list.append("Value %(value)r of field '%(fieldname)s' is "
                              "not a ip-address" % locals())


DEFAULT_FORMAT_VALIDATORS = {
    'date-time': validate_format_date_time,
    'date': validate_format_date,
    'time': validate_format_time,
    'utc-millisec': validate_format_utc_millisec,
    'ip-address': validate_format_ip_address,
}


class MetaSchemaValidator(type):
    ''' A metaclass that helps keeping track of the fields path
    '''

    def __new__(cls, name, bases, dct):
        for method_name, method in list(dct.items()):
            if method_name.startswith('validate_') and not method_name.startswith('validate_type_') and callable(method):

                def make_wrapper(method_name, method):
                    @wraps(method)
                    def wrapper(self, x, fieldname, schema, *a, **kw):
                        name = fieldname if not isinstance(fieldname, int) else '[%d]' % fieldname

                        if self.current_object and self.current_object[-1] is x:
                            pop_at_end = False
                            self.current_field[-1] = name
                        else:
                            pop_at_end = True
                            self.current_object.append(x)
                            self.current_field.append(name)

                        res = method(self, x, fieldname, schema, *a, **kw)

                        if pop_at_end:
                            self.current_field.pop()
                            self.current_object.pop()
                        return res
                    return wrapper

                dct[method_name] = make_wrapper(method_name, method)

        return super(MetaSchemaValidator, cls).__new__(cls, name, bases, dct)


class SchemaValidator(object):
    '''
    Validator largely based upon the JSON Schema proposal but useful for
    validating arbitrary python data structures.

    :param format_validators: optional dictionary of custom format validators
    :param required_by_default: defaults to True, set to False to make
        ``required`` schema attribute False by default.
    :param blank_by_default: defaults to False, set to True to make ``blank``
        schema attribute True by default.
    '''

    __metaclass__ = MetaSchemaValidator

    @property
    def current_field_name(self):
        current = u'.'.join(self.current_field[1:]) # we remove the first _data.
        return current if current else None

    def __init__(self, format_validators=None, required_by_default=True,
                 blank_by_default=False):
        if format_validators is None:
            format_validators = DEFAULT_FORMAT_VALIDATORS.copy()

        self._format_validators = format_validators
        self.required_by_default = required_by_default
        self.blank_by_default = blank_by_default
        self.error_list = []
        self.error_stack = []
        self.current_field = []
        self.current_object = []

    def get(self, x, field, default=None):
        try:
            return x[field]
        except KeyError:
            return default
        except IndexError:
            return default

    def push_error_stack(self):
        self.error_stack.append(self.error_list)
        self.error_list = []

    def pop_error_stack(self):
        last_error = self.error_list
        self.error_list = self.error_stack.pop()
        return last_error

    def register_format_validator(self, format_name, format_validator_fun):
        self._format_validators[format_name] = format_validator_fun

    def validate_type_string(self, val):
        return isinstance(val, _str_type)

    def validate_type_integer(self, val):
        return type(val) in _int_types

    def validate_type_number(self, val):
        return type(val) in _int_types + (float,)

    def validate_type_boolean(self, val):
        return type(val) == bool

    def validate_type_object(self, val):
        return isinstance(val, Mapping)

    def validate_type_array(self, val):
        return isinstance(val, (list, tuple))

    def validate_type_null(self, val):
        return val is None

    def validate_type_any(self, val):
        return True

    def _error(self, code, message=None, suppl=None):
        self.error_list.append((code, self.current_field_name, message, suppl))

    def validate_type(self, x, fieldname, schema, fieldtype=None):
        '''
        Validates that the fieldtype specified is correct for the given
        data
        '''

        # We need to know if the field exists or if it's just Null
        fieldexists = True
        try:
            value = x[fieldname]
        except KeyError:
            fieldexists = False
            value = None

        if fieldtype and fieldexists:
            if isinstance(fieldtype, (list, tuple)):
                # Match if type matches any one of the types in the list
                datavalid = False
                for eachtype in fieldtype:
                    self.push_error_stack()
                    self.validate_type(x, fieldname, eachtype, eachtype)
                    errs = self.pop_error_stack()
                    if not errs:
                        datavalid = True
                        break
                if not datavalid:
                    self._error('incorrect-type', fieldtype, self.get(x, fieldname))
                    return
            elif isinstance(fieldtype, dict):
                self.push_error_stack()
                self.__validate(fieldname, x, fieldtype)
                errs = self.pop_error_stack()
                if errs:
                    self.error_list += errs
            else:
                try:
                    type_checker = getattr(self, 'validate_type_%s' % fieldtype)
                except AttributeError:
                    raise SchemaError("Field type '%s' is not supported." %
                                      fieldtype)

                if not type_checker(value):
                    self._error('incorrect-type', fieldtype, self.get(x, fieldname))

    def validate_properties(self, x, fieldname, schema, properties=None):
        '''
        Validates properties of a JSON object by processing the object's
        schema recursively
        '''
        value = self.get(x, fieldname)
        if value is not None:
            if isinstance(value, dict):
                if isinstance(properties, dict):
                    for eachProp in properties:
                        self.__validate(eachProp, value, properties.get(eachProp))
                else:
                    raise SchemaError("Properties definition of field '%s' is "
                                      "not an object" % fieldname)

    def validate_items(self, x, fieldname, schema, items=None):
        '''
        Validates that all items in the list for the given field match the
        given schema
        '''
        value = self.get(x, fieldname)
        if value is not None:
            if isinstance(value, (list, tuple)):
                if isinstance(items, (list, tuple)):
                    if len(items) != len(value):
                        # resolve defaults now
                        for i, item in enumerate(items):
                            try:
                                value[i]
                            except IndexError:
                                # obviously it does not exists
                                if 'default' in item:
                                    value.append(item['default'])
                                # else:
                                # self.error_list.append(
                                #     "Failed to validate field '%s' "
                                #     "value missing for item %d" %
                                #     (fieldname, i)
                                # )
                                # return

                    if not 'additionalItems' in schema and len(items) != len(value):
                        self._error('incorrect-item-length')
                        # self._error("Length of list %(value)r for field "
                        #             "'%(fieldname)s' is not equal to length "
                        #             "of schema list", value, fieldname)
                        return
                    else:
                        for itemIndex in range(len(items)):
                            # self.push_error_stack()
                            self.__validate(itemIndex, value, items[itemIndex])
                            # errs = self.pop_error_stack()
                            # if len(errs) > 0:
                            # self._error('incorrect-type')
                            # self.error_list.append("Failed to validate field '%s' "
                            #               "list schema: %s" %
                            #               (fieldname, items[itemIndex]))
                            return
                elif isinstance(items, dict):
                    for i, eachItem in enumerate(value):
                        self.push_error_stack()
                        self.__validate(i, value, items)
                        errs = self.pop_error_stack()
                        if len(errs) > 1:
                            # a bit of a hack: replace reference to _data
                            # with 'list item' so error messages make sense
                            # FIXME should iterate on the errors to produce same result
                            # old_error = str(e).replace("field '_data'", 'list item')
                            # raise type(e)("Failed to validate field '%s' list "
                            #               "schema: %s" %
                            #               (fieldname, old_error))
                            for e in errs:
                                # e = e.replace("field '_data", 'list item ' + i)
                                self.error_list.append(e)
                            # self.error_list.append('Failed to validate one list item in %s on schema %s' % (eachItem, value))
                            return
                else:
                    raise SchemaError("Properties definition of field '%s' is "
                                      "not a list or an object" % fieldname)

    def validate_required(self, x, fieldname, schema, required):
        '''
        Validates that the given field is present if required is True
        '''
        # Make sure the field is present
        if fieldname not in x and required:
            self._error('missing-required')

    def validate_blank(self, x, fieldname, schema, blank=False):
        '''
        Validates that the given field is not blank if blank=False
        '''
        value = self.get(x, fieldname)
        if isinstance(value, _str_type) and not blank and not value:
            self._error('blank')
            # self._error("Value %(value)r for field '%(fieldname)s' cannot be "
            #             "blank'", value, fieldname)

    def validate_patternProperties(self, x, fieldname, schema,
                                   patternproperties=None):

        if patternproperties == None:
            patternproperties = {}

        value_obj = self.get(x, fieldname, {})

        for pattern, schema in patternproperties.items():
            for key, value in value_obj.items():
                if re.match(pattern, key):
                    self.validate(value, schema)

    def validate_additionalItems(self, x, fieldname, schema,
                                 additionalItems=False):
        value = self.get(x, fieldname)

        if not isinstance(value, (list, tuple)):
            return

        if isinstance(additionalItems, bool):
            if additionalItems or 'items' not in schema:
                return
            elif len(value) != len(schema['items']):
                #print locals(), value, len(value), len(schema['items'])
                # self._error("Length of list %(value)r for field "
                #             "'%(fieldname)s' is not equal to length of schema "
                #             "list", value, fieldname)
                self._error('incorrect-list-length')
                return

        remaining = value[len(schema['items']):]
        if len(remaining) > 0:
            self._validate(remaining, {'items': additionalItems})

    def validate_additionalProperties(self, x, fieldname, schema, additionalProperties=None):
        '''
        Validates additional properties of a JSON object that were not
        specifically defined by the properties property OR the patternProperties
        object.

        By default, the validator behaves like True was passed to additional,
        which means that we mostly want to use it with False or a schema.
        '''

        # Shouldn't be validating additionalProperties on non-dicts
        value = self.get(x, fieldname)
        if not isinstance(value, dict):
            return

        # If additionalProperties is the boolean value True then we accept
        # any additional properties.
        if isinstance(additionalProperties, bool) and additionalProperties:
            return

        if isinstance(additionalProperties, (dict, bool)):
            properties = schema.get("properties", [])
            patternProperties = schema.get('patternProperties', [])
            if properties is None:
                properties = {}
            if value is None:
                value = {}
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
                    self._error('forbidden-property', eachProperty)
                    return
                else:
                    # If it's an object, then we try to validate the value
                    # on the schema.
                    self.validate(value, additionalProperties)
        else:
            raise SchemaError("additionalProperties schema definition for "
                              "field '%s' is not an object" % fieldname)

    def validate_dependencies(self, x, fieldname, schema, dependencies=None):
        if self.get(x, fieldname) is not None:

            # handle cases where dependencies is a string or list of strings
            if isinstance(dependencies, _str_type):
                dependencies = [dependencies]
            if isinstance(dependencies, (list, tuple)):
                for dependency in dependencies:
                    if dependency not in x:
                        # self._error("Field '%(dependency)s' is required by "
                        #             "field '%(fieldname)s'",
                        #     None, fieldname, dependency=dependency)
                        self._error('dependency', dependency)
                        return
            elif isinstance(dependencies, dict):
                # NOTE: the version 3 spec is really unclear on what this means
                # based on the meta-schema I'm assuming that it should check
                # that if a key exists, the appropriate value exists
                for k, v in dependencies.items():
                    if k in x and v not in x:
                        # self._error("Field '%(v)s' is required by field "
                        #             "'%(k)s'", None, fieldname, k=k, v=v)
                        self._error('dependency', k, v)
                        return
            else:
                raise SchemaError("'dependencies' must be a string, "
                                  "list of strings, or dict")

    def validate_minimum(self, x, fieldname, schema, minimum=None):
        '''
        Validates that the field is longer than or equal to the minimum
        length if specified
        '''

        exclusive = schema.get('exclusiveMinimum', False)

        value = self.get(x, fieldname)
        if value is not None:
            if value is not None:
                if (type(value) in (int, float) and
                    (not exclusive and value < minimum) or
                    (exclusive and value <= minimum)):
                    self._error('less-than-minimum', minimum, value)
                    # self._error("Value %(value)r for field '%(fieldname)s' is "
                    #             "less than minimum value: %(minimum)f",
                    #             value, fieldname, minimum=minimum)

    def validate_maximum(self, x, fieldname, schema, maximum=None):
        '''
        Validates that the field is shorter than or equal to the maximum
        length if specified.
        '''

        exclusive = schema.get('exclusiveMaximum', False)

        value = self.get(x, fieldname)
        if value is not None:
            if (type(value) in (int, float) and
                (not exclusive and value > maximum) or
                (exclusive and value >= maximum)):
                self._error('more-than-maximum', maximum, value)
                # self._error("Value %(value)r for field '%(fieldname)s' is "
                #             "greater than maximum value: %(maximum)f",
                #             value, fieldname, maximum=maximum)

    def validate_maxLength(self, x, fieldname, schema, length=None):
        '''
        Validates that the value of the given field is shorter than or equal
        to the specified length
        '''
        value = self.get(x, fieldname)
        if isinstance(value, (_str_type, list, tuple)) and len(value) > length:
            self._error('too-long', length, len(value))
            # self._error("Length of value %(value)r for field '%(fieldname)s' "
            #             "must be less than or equal to %(length)d",
            #             value, fieldname, length=length)

    def validate_minLength(self, x, fieldname, schema, length=None):
        '''
        Validates that the value of the given field is longer than or equal
        to the specified length
        '''
        value = self.get(x, fieldname)
        if isinstance(value, (_str_type, list, tuple)) and len(value) < length:
            self._error('too-short', length, len(value))
            # self._error("Length of value %(value)r for field '%(fieldname)s' "
            #             "must be greater than or equal to %(length)d",
            #             value, fieldname, length=length)

    validate_minItems = validate_minLength
    validate_maxItems = validate_maxLength

    def validate_format(self, x, fieldname, schema, format_option=None):
        '''
        Validates the format of primitive data types
        '''
        value = self.get(x, fieldname)

        format_validator = self._format_validators.get(format_option, None)

        if format_validator and value:
            format_validator(self, fieldname, value, format_option)

        # TODO: warn about unsupported format ?

    def validate_pattern(self, x, fieldname, schema, pattern=None):
        '''
        Validates that the given field, if a string, matches the given
        regular expression.
        '''
        value = self.get(x, fieldname)
        if isinstance(value, _str_type):
            if not re.match(pattern, value):
                self._error('pattern-mismatch', pattern, fieldname)
                # self._error("Value %(value)r for field '%(fieldname)s' does "
                #             "not match regular expression '%(pattern)s'",
                #             value, fieldname, pattern=pattern)

    def validate_uniqueItems(self, x, fieldname, schema, uniqueItems=False):
        '''
        Validates that all items in an array instance MUST be unique
        (contains no two identical values).
        '''

        # If additionalProperties is the boolean value True then we accept
        # any additional properties.
        if isinstance(uniqueItems, bool) and not uniqueItems:
            return

        values = self.get(x, fieldname)

        if not isinstance(values, (list, tuple)):
            return

        hashables = set()
        unhashables = []

        for value in values:
            if isinstance(value, (list, dict)):
                container, add = unhashables, unhashables.append
            else:
                container, add = hashables, hashables.add

            if value in container:
                self._error('not-unique', value)
                # self._error(
                #     "Value %(value)r for field '%(fieldname)s' is not unique",
                #     value, fieldname)
            else:
                add(value)

    def validate_enum(self, x, fieldname, schema, options=None):
        '''
        Validates that the value of the field is equal to one of the
        specified option values
        '''
        value = self.get(x, fieldname)
        if value is not None:
            if not isinstance(options, Container):
                raise SchemaError("Enumeration %r for field '%s' must be a "
                                  "container", (options, fieldname))
            if value not in options:
                self._error('not-in-enumeration', options, value)
                # self._error("Value %(value)r for field '%(fieldname)s' is not "
                #             "in the enumeration: %(options)r",
                #             value, fieldname, options=options)

    def validate_title(self, x, fieldname, schema, title=None):
        if not isinstance(title, (_str_type, type(None))):
            raise SchemaError("The title for field '%s' must be a string" %
                             fieldname)

    def validate_description(self, x, fieldname, schema, description=None):
        if not isinstance(description, (_str_type, type(None))):
            raise SchemaError("The description for field '%s' must be a string"
                             % fieldname)

    def validate_divisibleBy(self, x, fieldname, schema, divisibleBy=None):
        value = self.get(x, fieldname)

        if not self.validate_type_number(value):
            return

        if divisibleBy == 0:
            raise SchemaError("'%r' <- divisibleBy can not be 0" % schema)

        if value % divisibleBy != 0:
            self._error('not-divisible-by', divisibleBy, value)
            # self._error("Value %(value)r field '%(fieldname)s' is not "
            #             "divisible by '%(divisibleBy)s'.",
            #             self.get(x, fieldname), fieldname, divisibleBy=divisibleBy)

    def validate_extends(self, x, fieldname, schema, extends=None):
        ''' Kind of an inheritance for schema validation : the
            field is to be checked against the provided schema
            in the extends property.
        '''
        self.validate_type(x, fieldname, schema, extends)

    def validate_disallow(self, x, fieldname, schema, disallow=None):
        '''
        Validates that the value of the given field does not match the
        disallowed type.
        '''
        self.push_error_stack()
        self.validate_type(x, fieldname, schema, disallow)
        errs = self.pop_error_stack()
        if len(errs) > 1:
            return
        # self._error("Value %(value)r of type %(disallow)s is disallowed for "
        #             "field '%(fieldname)s'",
        #             self.get(x, fieldname), fieldname, disallow=disallow)
        self._error('disallowed-type', disallow, self.get(x, fieldname))

    def validate(self, data, schema):
        '''
        Validates a piece of json data against the provided json-schema.
        Returns the validated data.
        '''
        result = self._validate(data, schema)
        if self.error_list:
            raise ValidationError(self.error_list)
        return result

    def _validate(self, data, schema):
        return self.__validate("_data", {"_data": data}, schema).get('_data')

    def __validate(self, fieldname, data, schema):

        if schema is not None:
            if not isinstance(schema, dict):
                raise SchemaError("Schema structure is invalid.")

            newschema = copy.copy(schema)

            if isinstance(data, dict) and fieldname not in data and 'default' in schema:
                data[fieldname] = schema['default']

            if 'optional' in schema:
                raise SchemaError('The "optional" attribute has been replaced'
                                  ' by "required"')
            if 'requires' in schema:
                raise SchemaError('The "requires" attribute has been replaced'
                                  ' by "dependencies"')

            if 'blank' not in schema:
                newschema['blank'] = self.blank_by_default

            self.validate_required(data, fieldname, newschema,
                newschema.pop('required', self.required_by_default))

            if 'type' in schema:
                self.validate_type(data, fieldname, newschema, newschema.pop('type'))

            for schemaprop in newschema:
                validatorname = "validate_" + schemaprop

                validator = getattr(self, validatorname, None)
                if validator:
                    validator(data, fieldname, newschema, newschema.get(schemaprop))

        return data

__all__ = ['SchemaValidator']
