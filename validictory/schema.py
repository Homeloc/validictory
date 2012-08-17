'''
    validation.py, an extension to validictory made to specifically deal
    with more python types and formats.
'''

from validator import SchemaValidator, validate
from extended import ExtendedSchemaValidator
from coercer import SchemaCoercer, ExtendedSchemaCoercer


def Either(*types, **kw):
    '''
        Example:
        Object(
            properties=dict(
                something=Either(
                    Boolean(),
                    Null,
                    required=True
                )
            )
        )
    '''
    return dict(
        type=types,
        **kw
    )


class MetaSchemaElement(type):

    def __new__(cls, name, bases, dct):

        attrs = dct.get('attrs', [])

        def makeattr(attr):
            methodname = attr[0]
            realname = attr[0]
            default = None

            if len(attr) == 2:
                default = attr[1]

            if len(attr) == 3:
                default = attr[2]
                realname = attr[1]

            def method(self, val=default):
                res = self.copy()
                res[realname] = val
                return res

            method.__name__ = methodname
            return method

        for attr in attrs:
            dct[attr[0]] = makeattr(attr)

        return super(MetaSchemaElement, cls).__new__(cls, name, bases, dct)


class SchemaElement(dict):
    type = ''

    attrs = [
        ('dependencies', []),
        ('default',)
    ]

    __metaclass__ = MetaSchemaElement

    def __init__(self):
        self['type'] = self.type

    def __call__(self, *a, **kw):
        newobj = self.__class__(*a, **kw)

        for k, v in self.items():
            if not k in newobj:
                newobj[k] = v

        return newobj

    def copy(self):
        newobj = self.__class__()
        for k, v in self.items():
            newobj[k] = v
        return newobj

    @property
    def required(self):
        cp = self.copy()
        cp['required'] = True
        return cp

    @property
    def not_required(self):
        cp = self.copy()
        cp['required'] = False
        return cp

    @property
    def nullable(self):
        ''' Should be the last one to be called '''
        return dict(
            type=[self, {'type': 'null'}]
        )

    def _validate(self, data, validator_cls=SchemaValidator,
             format_validators=None, required_by_default=False,
             blank_by_default=False, ignore_required=False):
        return validate(
            data,
            self,
            validator_cls=validator_cls,
            format_validators=format_validators,
            required_by_default=required_by_default,
            blank_by_default=blank_by_default,
            ignore_required=ignore_required
        )

    def validate(self, data, **kw):
        return self._validate(data, **kw)

    def coerce(self, data, validator_cls=SchemaCoercer, **kw):
        return self._validate(data, validator_cls=validator_cls, **kw)


class _Object(SchemaElement):
    type = 'object'

    attrs = [
        ('properties', {}),
        ('patterns', 'patternProperties', {}),
        ('additionalProperties', 'additionalProperties', True),
        ('min_props', 'minProperties', 0),
        ('max_props', 'maxProperties', 0),
    ]

    def __init__(self, *propdicts, **kw):
        super(_Object, self).__init__()
        self['properties'] = {}
        for propdict in propdicts:
            self['properties'].update(propdict)
        self['properties'].update(kw)

    def pattern(self, regexp, type):
        if not 'patternProperties' in self:
            self['patternProperties'] = {}
        self['patternProperties'][regexp] = type
        return self

    def require_either(self, *a):
        self['requireEither'] = a
        return self

    def merge(self, other):
        for k, v in other.get('properties', {}).items():
            self['properties'][k] = v

        if other.get('patternProperties', None) and not 'patternProperties' in self:
            self['patternProperties'] = {}
        for k, v in other.get('patternProperties', {}).items():
            self['patternProperties'][k] = v
        return self


class _StrictObject(_Object):
    ''' A variant of Object that disallows additional properties.
    '''

    def __init__(self, **kw):
        super(_StrictObject, self).__init__(**kw)
        self['additionalProperties'] = False


class _Array(SchemaElement):
    type = 'array'

    attrs = (
        ('min_items', 'minItems', 0),
        ('max_items', 'maxItems', 0),
        ('additional_items', 'additionalItems', True),
        ('unique_items', 'uniqueItems', True)
    )

    def __init__(self, items=None):
        self['type'] = 'array'
        if items:
            self['items'] = items


class _Number(SchemaElement):
    type = 'number'

    attrs = (
        ('min', 'minimum'),
        ('max', 'maximum'),
        ('divisible_by',),
        ('excl_min', 'exclusiveMinimum'),
        ('excl_max', 'exclusiveMaximum'),
    )


class _Integer(_Number):
    type = 'integer'


class _Boolean(SchemaElement):
    type = 'boolean'


class _Datetime(SchemaElement):
    type = 'datetime'


class _String(SchemaElement):
    type = 'string'

    attrs = (
        ('min_length', 'minLength', 0),
        ('max_length', 'maxLength', 0),
        ('format',),
        ('pattern',),
    )

    def enum(self, *args):
        cp = self.copy()
        enum = []
        for a in args:
            if isinstance(a, (tuple, list)):
                enum += a
            else:
                enum.append(a)
        cp['enum'] = enum
        return cp

    @property
    def allow_blank(self):
        cp = self.copy()
        cp['blank'] = True
        return cp

# Any is meant to be used as is, without instanciating it.
Any = {'type': 'any'}
Object = _Object()
StrictObject = _StrictObject()
Array = _Array()
Number = _Number()
Integer = _Integer()
Boolean = _Boolean()
String = _String()
Datetime = _Datetime()
