#!/usr/bin/env python

from validictory.validator import SchemaValidator, ValidationError, SchemaError, validate
from validictory.extended import ExtendedSchemaValidator
from validictory.coercer import SchemaCoercer, ExtendedSchemaCoercer
from validictory.schema import String, Object, Array, Number, Boolean
from validictory.schema import Any, Either, Datetime, Integer, StrictObject

__all__ = ['validate', 'coerce', 'SchemaValidator', 'ValidationError',
    'SchemaError', 'SchemaCoercer', 'ExtendedSchemaValidator', 'ExtendedSchemaCoercer',
    'String', 'Object', 'Array', 'Integer', 'Number', 'Boolean', 'Any',
    'Either', 'Datetime', 'StrictObject', 'Either',
    'validate'
]
__version__ = '0.9.7-homeloc'


if __name__ == '__main__':
    import sys
    import json
    if len(sys.argv) == 2:
        if sys.argv[1] == "--help":
            raise SystemExit("%s SCHEMAFILE [INFILE]" % (sys.argv[0],))
        schemafile = open(sys.argv[1], 'rb')
        infile = sys.stdin
    elif len(sys.argv) == 3:
        schemafile = open(sys.argv[1], 'rb')
        infile = open(sys.argv[2], 'rb')
    else:
        raise SystemExit("%s SCHEMAFILE [INFILE]" % (sys.argv[0],))
    try:
        obj = json.load(infile)
        schema = json.load(schemafile)
        validate(obj, schema)
    except ValueError as e:
        raise SystemExit(e)
