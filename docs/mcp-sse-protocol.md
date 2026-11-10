# 确定性 SSE/JSON-RPC 接入及执行验证

> 状态更正：历史的浏览器拒绝不等于官方 MCP API 被拒；最新实现与未完成项见文末 2026-11-10 更正。

初轮记录（2026-11-10）：基于官方示例流程，新增 `fast_transfer/mcp_sse.py`，接入现有 `mcp_share.FixtureTransport`、精确合成文件校验及 Job 锁/持久意图。**内存原始 HTTP/SSE 字节流验证已执行；实际服务连接、TLS、真实身份/对象/分享均未尝试。** 没有另建工作流/账本、LLM 循环或 supervisor，也没有读取凭据、迁移/重传原样例。

同日后续进展：已实现[回环专用真实 HTTPS/SSE 驱动](mcp-local-https.md)，21项真实本地传输测试通过；下文42项为初轮内存验证历史，外部入口仍锁定。

## 依赖和源码依据

对当前解释器仅查询 importlib.metadata，mcp/httpx/anyio/python-dotenv 均未安装；没有导入 SDK、安装或下载依赖制品。因此本轮选择可用标准库实现和可执行的原始协议层，而非运行官方 demo。**当时尚无联网驱动；现在默认构造器仍仅接受 ScriptedHTTP，后续新增独立回环工厂，外部驱动入口依旧锁定，不能当成可直接连接百度的客户端。**

流程参考 [baidu-netdisk/mcp 固定示例](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/client_demo/client_demo_sse.py)。保留 MIT 署名、许可证及 [NOTICE](../third_party/NOTICE.md)。同时只读核对官方锁定 mcp1.6.0 对应 [SDK SSE](https://github.com/modelcontextprotocol/python-sdk/blob/v1.6.0/src/mcp/client/sse.py)、[session](https://github.com/modelcontextprotocol/python-sdk/blob/v1.6.0/src/mcp/client/session.py)、[types](https://github.com/modelcontextprotocol/python-sdk/blob/v1.6.0/src/mcp/types.py)；逐文件 Git blob/SHA-256 保存在证据中，SDK 许可证亦保留，未安装或执行源码。

SDK 1.6.0 声明协议2024-11-05，initialize 后发送 notifications/initialized；SSE endpoint 使用 urljoin 并校验同 scheme/netloc。SDK 的 HTTP timeout 默认5秒、SSE read timeout默认300秒；其源码会记录 endpoint，debug 下还可能记录收发 message。它不是已审的无秘密日志驱动；这些单操作超时也不是硬任务截止。官方已有 uv.lock 的事实不变，但项目尚未采用/完整审查该锁或验证 Python3.14/SDK 运行兼容性。

本实现移除 LLM/千帆调用、dotenv/配置/令牌发现、参数/原始错误输出、自动重试与重连。AUTH_SLOT 仅为对象标记，没有字符串凭据；没有构造或发送含真实 token 的 URL。官方 SSE 查询参数认证的风险仍适用，未来真实 driver 必须独立审阅，不能假设 Authorization header 可替代。

## 确定性流程与范围

1. 原 Job 在锁内读取；只有原固定16字节合成文件的 simulated_cloud_verified 状态才进入协议。真实已上传 NCBI 样例没有因此被复制或转成合成凭证。
2. ScriptedHTTP 接受官方 SSE URL 的模拟 GET，校验状态200及 text/event-stream；消费碎片化字节、CRLF/注释/多行 data，读取 endpoint 事件。endpoint 仅接受同 HTTPS 精确主机、`/messages` 或 `/messages/`、单一有界 session_id；禁止跨域、userinfo、fragment、编码/额外认证查询和其他路径。
3. initialize(id1,协议2024-11-05)→notifications/initialized→tools/list(id2)。要求精确匹配本地三工具 discovery profile，没有 pagination 自动跟进；缺工具、额外所需参数、未知 schema 即停。该 schema 是保守测试 profile，不是假称已取得真实服务 schema。
4. 一次 user_info(id3)、精确 file_meta(id4)。metadata 的 fsids 在此测试 profile 是单一整数 ID 数组（README 示例亦为数值数组）；实际运行 schema 未确认，不能当真实接口全量契约。身份/应用/会话与文件 path/fsid/MD5/长度仍由已有 fixture 规则核对，不把 MCP 标准信封当可信账号/应用证明。
5. 复用现有 Job.save 先存 manual_review/未知意图，再仅一次 file_sharelink_set(id5)。参数仍只有 fsid_list 的 JSON 字符串 ID 数组、period7、pwd；任何其他对象/工具/参数在发包前拒绝。RPC异常、非成功状态、断流、超时、解析失败没有重发；重开同 Job 即使新 client 也不再建链。
6. 标准 JSON-RPC 必须2.0、精确整型响应 ID、result/error 互斥；generic RPC error 或 MCP isError 只作为错误，绝不映射成13998等权限含义。工具结果仅支持一个 TextContent 内的严格 JSON fixture 业务对象。非文本、多块、REST/Cookie envelope、未知业务包装均停在未验证；不猜测真实业务成功含义。
7. 最后清除缓冲并关闭驱动；关闭不确认时转 manual_review，不输出成功。公共 trace 只有方法/工具名/ID/参数键，不含参数值、响应、URL/会话查询或码。即使全部通过仍 candidate_unverified，真实认证/映射/分享/交付资格保持 false。

HTTP状态200/202仅用于本地 POST profile；此实现不是通用 MCP 兼容层：只支持显式 endpoint/message SSE 事件，拒绝 id/retry等未审语义、服务器主动请求/通知、未知协议和多页 schema。event≤16KiB、累计读取≤256KiB、行≤512、一次读取请求≤1024字节；预算默认5秒且至多30秒，只在协作检查点判断，不抢占永久阻塞 I/O。保守拒绝不证明真实服务不支持这些功能。

## 实际执行与测试矩阵

新增 **17项协议测试**，干净预期提交副本中连同受影响 MCP候选17项、工作流8项，共 **42项通过，零失败/错误/跳过**。初始41项通过，补充参数范围测试及完整故障分支后42项通过；没有本轮失败记录。历史未提交四项未复制/运行，没有重跑旧Go模型、M6或supervisor工程。

| 验证 | 实际执行 |
| --- | --- |
| 完整链路 | 逐字节分片，id/通知顺序及工具/参数键检查；只调用一次分享，既有 Job 留在人工检查 |
| SSE framing | CRLF、注释、多行 data、半包；坏UTF-8/重复字段/retry/EOF/事件上限/心跳洪泛拒绝 |
| 目的端/HTTP | HTTP/跨域/userinfo/百分号/fragment/令牌查询/路径漂移拒绝；模拟302/307/500与错误MIME不跟随 |
| 协议/发现 | 错ID、bool ID、重复JSON、RPC error、未知版本、缺工具、分页、未知必需字段均停 |
| 文件/范围 | wire解码后的 uk/对象漂移无分享；其他 fsids/工具/额外认证参数在I/O前拒绝 |
| 分享故障 | TextContent异常、REST包装、isError、POST302/500、TimeoutError；结果未知且同Job新会话零重发 |
| 关闭/隐私 | deadline/closed 后无新I/O；close=false不报成功；输出/trace/state/repr无合成链接、提取码及原始错误 |

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_mcp_sse test_mcp_share test_workflow
```

沿用受审 runner：seccomp 内核禁网，实际 socket=EPERM；空 HOME/配置、显式最小环境、-I -S -B、关闭额外FD。**没有文件系统沙箱**，文件范围由审查后的代码及 TemporaryDirectory约束。没有本地网络服务器或外部连接；HTTP状态、TimeoutError、业务结果是合成注入，未执行真实TCP/TLS/SSE SDK。日志、源码/许可证哈希及固定来源见[JSON证据](validation/mcp-sse-protocol-2026-11-10.json)和[日志](validation/mcp-sse-protocol-2026-11-10.txt)。

## 未完成与最小下一步

真实连接首要仍缺原 Browser Use site safety gate 对同一目的的可验证允许依据；本轮开发授权不解除它，也不以新驱动/主机绕行。接下来还需要明确兼容应用/原精确 NCBI对象的权限、真实业务响应/映射契约，以及逐次确认的短期凭据使用和私密返回方式。不能从已上传成功推导当前 token有效或 MCP/分享权益。

具体下一步是先取得允许渠道/实际阶段范围，再基于已实现的本地驱动机械层审阅外部路由、TLS公共CA/主机检查、无跨域认证跳转、无代理/日志泄漏、受控超时及真实数据流；不能直接放开 ScriptedHTTP 类型门或安装SDK即宣称可用。其后才可能依次验证实际服务连接、真实身份/精确对象、单次分享及境内领取，分别记录。这些现在均未尝试；原上传保留、5GiB保留线不变，PR保持草稿、不部署。

## 2026-11-10 纠正与官方驱动开发进展

此前把 Mac 浏览器打开 `https://pan.baidu.com/` 的 Browser Use site safety gate 拒绝泛化为官方 MCP API 的前置封锁，依据不足，相关历史段落中的“先取得原控制允许依据/联系维护方”不再作为官方 API 开发或验证的通用前提。不能重试被拒网页或用另一浏览器/CDP完成同一被拒网页访问；官方 API 的具体请求若遇新的控制拒绝，停止该操作，不绕路。

新增 `OfficialHTTPSDriver` 和独立 `SSEClient.for_official_readonly`：固定官方 SSE 域名/443，只接受调用者显式传入的临时 access_token，不自动读文件、环境、浏览器或回调，不执行 OAuth/刷新。使用系统 CA、官方域名 SNI/主机校验与 TLS≥1.2；首次请求解析官方域名，拒绝非公共地址，单次会话固定一个地址，不自动切换重试。GET 仅向固定官方 SSE 路径提交 URL 编码令牌；后续消息仅允许同 origin 的受限 session endpoint，无跳转或代理、无 LLM。关闭时释放令牌引用，不宣称内存安全擦除。继承现有时限/watchdog/关闭及脱敏；目前错误码仍沿用部分 `mcp_local_*`，不据错误码判断网络范围。

此阶段允许协议握手/工具清单及 user_info/file_meta 调用；所有分享和其他工具在发包前拒绝。它是实际外部传输代码，不是已完成的真实分享适配器：尚未把真实身份、精确对象、服务响应与现有 Job 持久单次意图接线。现有 fixture 分享保护继续保持，不能直接把真实驱动塞入 fixture 工厂。

新增13项合成凭据检查在 seccomp 禁网 runner 通过；真实 socket/TLS 被 mock，不构成官方实网证据。因共享 GET 路径增加了 override，针对受影响的21项真实本地 TCP/TLS 测试回归通过，零失败/跳过；未重跑旧42项内存测试。官方 DNS/连接/认证/工具契约/身份/原对象/分享/领取均未尝试，没有读取真实凭据或重传样例。

DNS调用者等待有界，但系统解析线程不能强制取消，超时后可能短期继续运行；线程不持有驱动或令牌。系统 CA 加载与 DNS 环境是本机信任边界，不宣称隔离全部宿主配置。查询令牌会到官方服务，客户端不记录不代表官方服务端不记录。

下一步：从既有可信私有任务收据确定精确原对象/账号/应用和允许使用的凭据来源；明确一次临时读取/内存使用并向官方 SSE 提交的权限，不扫描秘密、不要求聊天贴令牌，不新建授权。确认该凭据兼容 MCP，取得实际只读响应再实现真实身份/对象 decoder 和持久单次分享接线；未知结果不重发。用户分享意图已明确，无需再泛问是否想分享。
