"""Conservative MD5 normalization adapted from BaiduPCS-Go DecryptMD5.

Copyright iikira; Apache-2.0, see third_party/baidupcs-go/LICENSE.
Source: qjfoidnh/BaiduPCS-Go at 1b9131817aaf8ca7dee24bc00e33ebc4c7a5cc73,
baidupcs/util.go. Modified: Python implementation, strict ASCII/type/length
and marker checks; malformed values reject instead of being passed through.
This is a representation transform, not a new content read or authenticity proof.
"""
import re


def normalize_md5(value):
    if type(value) is not str or len(value)!=32:
        return None
    if re.fullmatch('[0-9a-fA-F]{32}',value):
        return value.lower()
    if not 'g'<=value[9]<='v':
        return None
    restored=value[:9]+format(ord(value[9])-ord('g'),'x')+value[10:]
    if not re.fullmatch('[0-9a-f-]{32}',restored):
        return None
    xored=''.join(format((0 if c=='-' else int(c,16))^(i&15),'x') for i,c in enumerate(restored))
    return xored[8:16]+xored[:8]+xored[24:]+xored[16:24]
