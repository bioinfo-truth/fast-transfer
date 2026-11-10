import unittest
from fast_transfer.baidu_md5 import normalize_md5

class BaiduMD5Tests(unittest.TestCase):
    def test_fixed_obfuscated_vector(self):
        self.assertEqual(normalize_md5('888888888o8888888888888888888888'),'0123456789abcdef0123456789abcdef')
    def test_plain_hex_and_uppercase(self):
        self.assertEqual(normalize_md5('ABCDEF0123456789ABCDEF0123456789'),'abcdef0123456789abcdef0123456789')
    def test_invalid_markers_types_and_lengths(self):
        for x in (None,True,7,'','a'*31,'z'*32,'888888888w8888888888888888888888','💧'*32):
            self.assertIsNone(normalize_md5(x))
    def test_all_sixteen_markers_roundtrip_synthetic_known_content(self):
        for n in range(16):
            plain=format(n,'x')*32
            swapped=plain[8:16]+plain[:8]+plain[24:]+plain[16:24]
            encoded=''.join(format(int(c,16)^(i&15),'x') for i,c in enumerate(swapped))
            encoded=encoded[:9]+chr(ord('g')+int(encoded[9],16))+encoded[10:]
            self.assertEqual(normalize_md5(encoded),plain)
