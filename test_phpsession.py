import unittest
import math

import phpsession

u = phpsession.unserialize


class TestPhpSession(unittest.TestCase):
    def test_unserialize_constants(self):
        self.assertIs(None, u("N;"))
        self.assertIs(True, u("b:1;"))
        self.assertIs(False, u("b:0;"))

    def test_unserialize_integers(self):
        self.assertEquals(42, u("i:42;"))
        self.assertEquals(-30, u("i:-30;"))

    def test_unserialize_doubles(self):
        self.assertEquals(3.141592, u("d:3.141592;"))
        self.assertEquals(-3.141592, u("d:-3.141592;"))
        self.assertTrue(math.isnan(u("d:NAN;")))
        self.assertTrue(math.isinf(u("d:INF;")))
        self.assertTrue(math.isinf(u("d:-INF;")))

    def test_unserialize_strings(self):
        self.assertEquals("string", u("s:6:\"string\";"))
        self.assertEquals("str\"ing", u("s:7:\"str\"ing\";"))
        self.assertEquals("bin\x00\x01", u("s:5:\"bin\x00\x01\";"))

        # PHP never seems to generate such strings, but is able
        # to unserialize them.
        self.assertEquals("bin\x00\x01", u("S:5:\"bin\\00\\01\";"))

    def test_unserialize_arrays(self):
        self.assertEquals([1, 2, 3], u("a:3:{i:0;i:1;i:1;i:2;i:2;i:3;}"))
        self.assertEquals({"a": 1, 0: 2}, u("a:2:{s:1:\"a\";i:1;i:0;i:2;}"))

        self.assertEquals({"a": 1, "b": 2},
                          u("a:2:{s:1:\"a\";i:1;s:1:\"b\";i:2;}"))

    def test_unserialize_object(self):
        thing = u("O:5:\"Thing\":3:{s:4:\"publ\";s:6:\"public\";"
                  "s:7:\"\x00*\x00prot\";s:9:\"protected\";"
                  "s:11:\"\x00Thing\x00priv\";s:7:\"private\";}")

        self.assertTrue(isinstance(thing, phpsession.PHPObject))
        self.assertEquals("Thing", thing.class_name)
        self.assertEquals("public", thing.publ)
        self.assertEquals("protected", thing.prot)
        self.assertEquals("private", thing.priv)

    def test_unserialize_stdclass(self):
        instance = u("o:1:\"s:4:\"prop\";s:5:\"value\";}")
        self.assertTrue(isinstance(instance, phpsession.PHPObject))
        self.assertEquals("stdClass", instance.class_name)
        self.assertEquals("value", instance.prop)

    def test_unserialize_arrayobject(self):
        # ArrayObject has a custom serialize/unserialize function
        array = u("C:11:\"ArrayObject\":45:{x:i:0;"
                  "a:3:{i:0;i:1;i:1;i:2;i:2;i:3;};m:a:0:{}}")
        self.assertTrue(isinstance(array, phpsession.PHPObject))
        self.assertEquals("ArrayObject", array.class_name)
        self.assertEquals([1, 2, 3], array.array)

    def test_unserialize_custom(self):
        instance = u("C:17:\"SerializableClass\":11:{some string}")
        self.assertTrue(isinstance(instance, phpsession.PHPObject))
        self.assertEquals("SerializableClass", instance.class_name)
        self.assertEquals("some string", instance._serialized)

    def test_session(self):
        session = phpsession.loads("foo|a:2:{i:0;i:1;i:1;i:2;}"
                                   "bar|a:3:{i:0;i:1;i:1;i:2;i:2;i:3;}")
        self.assertEqual([1, 2], session["foo"])
        self.assertEqual([1, 2, 3], session["bar"])

    @unittest.skip("not yet implemented")
    def test_unserialize_references(self):
        a, b = u("a:2:{i:0;O:8:\"stdClass\":2:{s:1:\"a\";r:2;s:1:\"b\";i:10;}"
                 "i:1;O:8:\"stdClass\":1:{s:1:\"a\";r:5;}}")
        self.assertIs(a, a.a)
        self.assertIs(b, b.a)

if __name__ == "__main__":
    unittest.main()
