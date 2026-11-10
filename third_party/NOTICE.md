# MCP protocol references

The deterministic connection sequence in `fast_transfer/mcp_sse.py` is adapted
from the MIT-licensed baidu-netdisk/mcp example, commit
`b3983d330fea79c7b72e6b7014803e1830148d2c`,
`src/baidu-netdisk/client_demo/client_demo_sse.py`.
Copyright (c) 2025 baidu-netdisk. License: `baidu-netdisk-mcp/LICENSE`.

The SSE framing and session sequence were reviewed against the MIT-licensed
modelcontextprotocol/python-sdk v1.6.0 (`src/mcp/client/sse.py`,
`src/mcp/client/session.py`, `src/mcp/types.py`). License: `python-sdk/LICENSE`.
No SDK code is installed or imported. No upstream client, LLM loop, credential
configuration, logging or retry machinery is executed or bundled here.

# BaiduPCS-Go MD5 normalization

`fast_transfer/baidu_md5.py` adapts `DecryptMD5` from
qjfoidnh/BaiduPCS-Go, commit `1b9131817aaf8ca7dee24bc00e33ebc4c7a5cc73`,
`baidupcs/util.go`, Copyright iikira, Apache License 2.0.
The Python implementation adds stricter input validation. License in
`third_party/baidupcs-go/LICENSE`.
