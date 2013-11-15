from StringIO import StringIO
import string


class SessionData:
    PS_DELIMITER = "|"
    PS_UNDEF_MARKER = "!"

    def __init__(self, data):
        self.data = data
        self.length = len(data)

    def values(self):
        i = 0
        while i < self.length:
            delim = self.data.find(self.PS_DELIMITER, i)
            if delim == -1:
                break

            key = self.data[i:delim]
            value, value_len = self.unserialize(delim + 1)

            yield key, value

            i = delim + 1 + value_len

        if i < self.length:
            raise Exception("Unable to decode session: trailing data")

    def unserialize(self, offset):
        if self.data[offset] == self.PS_UNDEF_MARKER:
            return None, 1

        stream = StringIO(self.data[offset:])
        try:
            value = unserialize(stream)
            return value, stream.tell()
        except AssertionError as ex:
            raise Exception("Unable to decode session: %s at offset %d" %
                            (ex, offset + stream.tell()))


class PHPObject:
    def __init__(self, class_name, **kwargs):
        self.__class_name = class_name
        self.__attributes = kwargs

        self.__protected = {}
        self.__private = {}
        self.__public = {}

        for key, value in kwargs.iteritems():
            if key.startswith("\x00"):
                class_name, _, property_name = key[1:].partition("\x00")
                if class_name == "*":   # protected
                    self.__protected[property_name] = value
                else:
                    self.__private[(class_name, property_name)] = value
            else:
                self.__public[key] = value

    @property
    def class_name(self):
        return self.__class_name

    def get_attributes(self):
        return self.__attributes

    def __getattr__(self, name):
        if name in self.__public:
            return self.__public[name]
        if name in self.__protected:
            return self.__protected[name]
        for (class_name, property_name), value in self.__private.iteritems():
            if property_name == name:
                return value
        raise AttributeError(name)

    def __repr__(self):
        values = self.__attributes.items()
        args = [repr(self.__class_name)] + ["%s=%r" % i for i in values]
        return "PHPObject(%s)" % (", ".join(args))


def expect(stream, value):
    actual = stream.read(len(value))
    assert actual == value, "expected %r, got %r" % (value, actual)


def read_iv(stream, endchar=";"):
    """Read a signed integer value from the stream."""

    c = stream.read(1)
    if c == "-":
        sign = -1
        c = stream.read(1)
    elif c == "+":
        sign = 1
        c = stream.read(1)
    else:
        sign = 1

    value = 0
    while c in string.digits:
        value = value * 10 + int(c)
        c = stream.read(1)

    assert c == endchar, "read_iv: expected %r, got %r" % (endchar, c)
    return sign * value


def read_uiv(stream, endchar=";"):
    """Read a unsigned integer value from the stream."""

    c = stream.read(1)
    if c == "+":
        c = stream.read(1)

    value = 0
    while c in string.digits:
        value = value * 10 + int(c)
        c = stream.read(1)

    assert c == endchar, "read_uiv: expected %r, got %r" % (endchar, c)
    return value


def unserialize_str(stream, length):
    """Unserialize a string, processing any character escapes."""

    output = ""
    for i in range(length):
        c = stream.read(1)
        if c == "\\":
            output += chr(int(stream.read(2), 16))
        else:
            output += c
    return output


def read_nested_data(stream, elements, is_object=False, start_char="{"):
    """Reads a list of key, value pairs from the stream."""

    expect(stream, start_char)

    values = []
    for i in range(elements):
        key = unserialize(stream)
        assert isinstance(key, (basestring, int)), \
            "array or object key should be integer or string"

        if is_object:
            key = str(key)

        value = unserialize(stream)
        values.append((key, value))

    expect(stream, "}")

    return values


def unserialize_arrayobject(stream):
    """Reads and unserializes an PHP ArrayObject from the stream."""

    expect(stream, "x:")
    flags = unserialize(stream)

    peek = stream.read(1)
    stream.seek(stream.tell() - 1)

    if peek == "m":
        array = None
    elif peek in "aOC":
        array = unserialize(stream)
    else:
        raise ValueError("ArrayObject: expected 'm', array or object")
    expect(stream, ";")

    expect(stream, "m:")
    members = unserialize(stream)

    return PHPObject("ArrayObject", flags=flags, array=array, members=members)


custom_unserialize = {
    "ArrayObject": unserialize_arrayobject
}


def unserialize(stream):
    if isinstance(stream, basestring):
        stream = StringIO(stream)

    typechar = stream.read(1)

    # Allow N; for NULL
    if typechar == "N":
        expect(stream, ";")
    else:
        expect(stream, ":")

    if typechar in "Rr":
        id_ = read_iv(stream) - 1
        raise NotImplementedError("Reference")

    elif typechar == "N":
        return None

    elif typechar == "b":
        value = stream.read(1)
        expect(stream, ";")
        return value == "1"

    elif typechar == "i":
        value = read_iv(stream)
        return value

    elif typechar == "d":
        c = stream.read(1)
        value = ""
        while c != ";":
            value += c
            c = stream.read(1)
        assert c == ";", "double: expected ';', got %r" % (endchar, c)
        # Just convert ot float, this also works for NaN and [+-]Inf
        return float(value)

    elif typechar == "s":
        length = read_uiv(stream, ":")
        expect(stream, "\"")
        value = stream.read(length)
        expect(stream, "\";")
        return value

    elif typechar == "S":
        length = read_uiv(stream, ":")
        expect(stream, "\"")
        value = unserialize_str(stream, length)
        expect(stream, "\";")
        return value

    elif typechar == "a":
        length = read_iv(stream, ":")
        values = read_nested_data(stream, length)

        keys = [k for (k, v) in values]
        if sorted(keys) == range(length):
            return [v for (k, v) in values]
        else:
            return dict(values)

    elif typechar in "oOC":
        if typechar == "o":
            class_name = "stdClass"
        else:
            length = read_uiv(stream, ":")
            expect(stream, "\"")
            class_name = stream.read(length)
            expect(stream, "\"")
            expect(stream, ":")

        if typechar == "C":
            length = read_uiv(stream, ":")
            expect(stream, "{")
            if class_name in custom_unserialize:
                obj = custom_unserialize[class_name](stream)
            else:
                serialized = stream.read(length)
                obj = PHPObject(class_name, _serialized=serialized)
            expect(stream, "}")
            return obj

        length = read_iv(stream, ":")
        start_char = "\"" if typechar == "o" else "{"
        values = dict(read_nested_data(stream, length, True, start_char))
        return PHPObject(class_name, **values)

    else:
        raise ValueError("Unknown type character '%s'" % typechar)


def serialize(obj):
    raise NotImplemented


def load(fp):
    return loads(fp.read())


def loads(string):
    data = SessionData(string)
    return dict(data.values())


def dump(data, fp):
    raise NotImplemented


def dumps(data):
    raise NotImplemented
