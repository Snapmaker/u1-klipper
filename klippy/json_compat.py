# JSON compatibility layer: prefer orjson for performance, fallback to stdlib.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# orjson is a high-performance JSON library (3-10x faster than stdlib json).
# It returns bytes from dumps() instead of str, and has different API for
# indent/separators. This module provides a compatible interface that:
#   - Uses orjson when available for maximum performance
#   - Falls back to stdlib json when orjson is not installed
#   - Maintains identical output behavior in both cases

import json as _stdlib_json


class _StdlibEncoder(_stdlib_json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, tuple):
            return list(obj)
        try:
            import numpy
            if isinstance(obj, (numpy.floating, numpy.integer)):
                return obj.item()
            if isinstance(obj, numpy.bool_):
                return bool(obj)
            if isinstance(obj, numpy.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _stdlib_dumps(obj, separators=None, indent=None, sort_keys=False):
    kwargs = {'cls': _StdlibEncoder}
    if separators is not None:
        kwargs['separators'] = separators
    if indent is not None:
        kwargs['indent'] = indent
    if sort_keys:
        kwargs['sort_keys'] = True
    return _stdlib_json.dumps(obj, **kwargs)


def _stdlib_dumps_bytes(obj, separators=None, sort_keys=False):
    kwargs = {'cls': _StdlibEncoder, 'separators': (',', ':')}
    if separators is not None:
        kwargs['separators'] = separators
    if sort_keys:
        kwargs['sort_keys'] = True
    return _stdlib_json.dumps(obj, **kwargs).encode('utf-8')


try:
    import orjson as _orjson

    def _default(obj):
        if isinstance(obj, tuple):
            return list(obj)
        try:
            import numpy
            if isinstance(obj, (numpy.floating, numpy.integer)):
                return obj.item()
            if isinstance(obj, numpy.bool_):
                return bool(obj)
            if isinstance(obj, numpy.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        raise TypeError

    _ENCODE_ERRORS = (TypeError, ValueError)
    if hasattr(_orjson, 'JSONEncodeError'):
        _ENCODE_ERRORS = (TypeError, ValueError, _orjson.JSONEncodeError)

    def dumps(obj, separators=None, indent=None, sort_keys=False):
        if indent is not None and indent != 2:
            return _stdlib_dumps(obj, separators=separators,
                                 indent=indent, sort_keys=sort_keys)
        opts = 0
        if sort_keys:
            opts |= _orjson.OPT_SORT_KEYS
        if indent is not None:
            opts |= _orjson.OPT_INDENT_2
        try:
            return _orjson.dumps(obj, option=opts, default=_default).decode('utf-8')
        except _ENCODE_ERRORS:
            return _stdlib_dumps(obj, separators=separators,
                                 indent=indent, sort_keys=sort_keys)

    def dumps_bytes(obj, separators=None, sort_keys=False):
        opts = 0
        if sort_keys:
            opts |= _orjson.OPT_SORT_KEYS
        try:
            return _orjson.dumps(obj, option=opts, default=_default)
        except _ENCODE_ERRORS:
            return _stdlib_dumps_bytes(obj, separators=separators,
                                       sort_keys=sort_keys)

    def loads(s):
        try:
            return _orjson.loads(s)
        except ValueError:
            return _stdlib_json.loads(s)

    HAS_ORJSON = True

except ImportError:

    def dumps(obj, separators=None, indent=None, sort_keys=False):
        return _stdlib_dumps(obj, separators=separators,
                             indent=indent, sort_keys=sort_keys)

    def dumps_bytes(obj, separators=None, sort_keys=False):
        return _stdlib_dumps_bytes(obj, separators=separators,
                                   sort_keys=sort_keys)

    def loads(s):
        return _stdlib_json.loads(s)

    HAS_ORJSON = False
