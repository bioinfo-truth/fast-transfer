# MCP 显式对象绑定与候选单次分享接线

2026-11-10：新增 `fast_transfer/mcp_binding.py`。本轮不读真实令牌、不连接官方业务服务、不创建真实分享；所有测试对象和响应均为合成数据。不能把候选解码或持久意图测试称为真实认证。

`ExpectedObject` 显式接收任务、预期账号、应用、fsid、路径、大小、MD5、既有本地回读 SHA256 和 Job mapping 摘要，默认 repr 不显示值，不发现配置或扫描秘密。这些输入是期望值，不能自证来源或权限。路径必须位于声明的应用目录，但目录字符串不证明 OAuth 应用归属。

`SSEClient.for_official_readonly(driver, expected=...)` 现在返回 `BoundSession`，精确请求传入的一个文件 ID，不再调用只支持固定测试 ID 的旧工具层。官方模式只审阅 user_info/file_meta 的保守候选 inputSchema；schema 不符时在读账号/对象前停止。官方会话与底层 HTTP 驱动均禁止分享，无 caller boolean 可启用真实副作用。

`decode_result` 严格处理 MCP CallToolResult：仅一个 TextContent、布尔 isError、受限 JSON、重复键/过大/过深/NaN 拒绝；不从文字/Markdown猜 JSON，不猜 errno/data/权限码。单个 JSON 文本作为业务内容只是明确的候选 profile，尚未证实为官方实际返回。账号只匹配 uk；元数据逐项匹配唯一 fsid/path/size/MD5，拒绝重复文件。README 未声明 SHA256，不能把本地回读哈希写成服务返回。

`stage_candidate_share` 复用现有 Job 的 flock、read/save、fsync/replace 与 manual_review 状态。仅精确 ScriptedHTTP 的候选会话可以进入：核对 Job/mapping/本地双哈希期望→读取候选身份/精确文件→保存未知意图→单次模拟创建。保存失败无创建；创建超时、错误或信封未知后保留未知，新会话/新进程重开同 Job 无请求重放；不落盘链接、码或私有账号/文件 ID，不开启 delivery。关闭未确认显示 manual_review。现有 Job 仍是 simulation 模式，没有用 JSON 声明真实权限，也没有新增真实账本或自动重置/补偿。

## 实际验证

干净预期提交副本执行：新增绑定17项 + 受工厂签名影响的官方驱动13项 + 受 schema review hook 影响的旧 SSE17项，共47项通过，零失败/跳过。明确包含真实子进程重开任务、Job 锁竞争和保存失败。其余协议网络为内存响应，官方 socket/TLS/DNS为 mock；本轮没有真实本地 TLS 或官方网络测试，没有重跑旧42项完整组合冒充实网。证据见 [JSON](validation/mcp-binding-2026-11-10.json) 与 [完整输出](validation/mcp-binding-2026-11-10.txt)。

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_mcp_binding test_mcp_official_http test_mcp_sse
```

## 精确未完成条件

| 缺口 | 当前依据与影响 |
| --- | --- |
| 真实业务内容信封及 inputSchema | [官方固定 README](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)列字段，未给完整 CallToolResult/JSON内部成功和拒绝示例或工具 inputSchema；当前 profile 不兼容即停，不猜测解码 |
| 凭据与应用权限来源 | user_info 仅列 uk/avatar_url/vip_type，无 app_id/client_id/scope；需明确获准临时使用的凭据来源及 MCP兼容性/应用权限，不能用 uk 匹配、目录名称或旧上传成功代替 |
| 原对象可信定位 | 运行前需由既有可信私有收据提供预期账号、应用、精确 fsid/path、长度/双哈希与任务关联；显式接口已具备，本轮未读取私有记录，不发布这些标识 |
| 分享对象映射与结果核实 | README 的 link/short_url/period/pwd 不包含 shareid/owner/fsids 映射或明确查询核实接口；候选结果保持未核实，真实分享 gate 未放开，也不编造撤销/重查能力 |

浏览器打开网盘网页的既有拒绝不能泛化为官方 MCP API 被拒；不重试被拒网页，官方具体操作若获新的拒绝则停止，不绕路。本轮未收到官方业务拒绝，也未发生需要补偿的真实创建。用户分享意图已明确；下一步应确认上述具体输入和权限，不泛问是否想分享、不要求在聊天贴令牌、不新建 OAuth。

后续状态：[官方端点无凭据可及性已实测](mcp-reachability.md)，HTTP200事件流响应头已收到，认证/业务仍未尝试。

后续协议实测：无凭据SSE与initialize已通过，实际路由为同域 `/message` + `sessionId`；生产旧profile尚未适配。见[实测分层记录](mcp-reachability.md)，不代表业务认证成功。

最新：[正式路由已接线，无凭据tools/list实测返回空列表](mcp-official-discovery.md)；具体工具schema、认证和原对象权限仍未验证。
