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
