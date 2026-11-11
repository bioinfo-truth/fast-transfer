# 候选 HTTP/SSE 驱动：真实本地 TCP/TLS 验证

> 状态更正：历史的浏览器拒绝不等于官方 MCP API 被拒；最新实现与未完成项见文末 2026-11-10 更正。

2026-11-10，本轮在上一轮字节协议层上新增 `mcp_http.LocalHTTPSDriver`，通过标准库 socket/SSL/http.client 执行真正 HTTPS GET、持久 SSE 读取和独立 POST，接入既有文件核对及 Job 单次分享意图。**21项真实本地传输测试通过，零失败/错误/跳过。没有访问百度，没有实际认证、分享或领取。** 上一轮42项内存测试没有重跑，不能与本轮相加冒充新的服务验证。

## 生产与测试入口分离

- 原 `SSEClient(driver)` 仍只接受精确 ScriptedHTTP；未简单移除类型门。新增 `SSEClient.for_local_fixture` / `exercise_local_fixture` 只接受精确 LocalHTTPSDriver；固定物理目的地为数值回环地址、仅端口可由测试注入，没有任意主机/DNS/凭据参数。外部 `external_driver()` 和原 `live_connect()` 始终拒绝，且测试证明拒绝发生在创建 socket 前。
- 本地工厂使用自己的 HTTPS origin，服务给出的消息 endpoint 必须同 origin；不会将官方域名重定向、代理或映射到本地。官方站点拒绝没有被尝试或绕过。本地服务只返回固定16字节合成任务数据，与原已上传 NCBI 对象无关，不复制/迁移/重传原样例。
- `live_connected=false` 兼容字段表示外部服务未连接；新增 `external_service_connected=false`、`transport_scope=local-loopback-tls` 和 `local_tls_connected` 明确记录本地 TLS 是否实际建立。TLS成功只认证本轮测试证书，不是百度账号/AppID/文件来源证明。

## 实现及安全边界

| 范围 | 已实现 |
| --- | --- |
| TLS | 证书必须验证、主机名必须检查、minimum TLS≥1.2；每次建连重新检查 context，拒绝启用 keylog 的 context；本地成功协商 TLS1.3 |
| 实际连接 | AF_INET socket 直连数值回环，不读取代理/凭据环境，不调用真实 DNS；先登记原始 socket，SSL包装后登记 SSL socket，再做握手，以便 deadline/close 只中断自己拥有的连接 |
| HTTP | GET只接受200与event-stream MIME；POST只接受200/202，其他状态直接拒绝，没有redirect/reconnect/retry；不处理或转发Location、Set-Cookie等认证状态 |
| 载荷 | 单POST≤16KiB，单次读取请求≤1024字节，总SSE≤256KiB，每driver最多6个POST；已有协议字节、行数与schema限制不变 |
| 响应头 | 拒绝重复关键头、Content-Length/Transfer-Encoding冲突与非identity编码；解析后头总量≤16KiB、数量≤32。标准库先解析头，不能把此值说成解析前分配上界，仍受标准库行/数量上限及watchdog约束 |
| 停止 | socket空闲超时与独立driver总预算watchdog；预算到时shutdown自己登记的socket，涵盖TLS握手、头部滴送、SSE读和POST等待；close取消并等待timer、关闭资源，仍有在途调用或其他close未完成则不确认 |
| 隐私 | 没有LLM、配置发现、token provider、参数/原始响应/异常日志；公开trace只有方法/工具名/ID，不含URL、session查询、参数值、链接/码。默认debug=0，TLS keylog context拒绝 |
| 分享 | 继续由原Job锁/先持久意图保护。测试服务接收分享后ACK超时或重定向/损坏返回，均保持未知；同Job新driver不发新GET/POST，不重发创建 |

driver默认socket idle timeout0.5秒、总预算3秒，允许显式0.05–30秒；协议自身仍有协作预算。watchdog使用本进程线程与socket shutdown，不是OS硬实时调度，也不能取消远端已受理动作；close未确认要保持人工检查，不能由本机连接关闭推断远端无副作用。未对任意不合作Python/C调用或互联网复杂故障承诺停止SLO。

## 实际测试矩阵

| 新测试 | 实际执行/结果 |
| --- | --- |
| 完整TLS/HTTP/SSE流程 | 自建TLS服务真实收1个GET和6个POST（initialize、通知、list_tools、user_info、file_meta、share）；合成创建计数1，结果仍candidate_unverified；同Job新driver零I/O |
| 信任链/主机名 | 不信任自签证书、信任但SAN不匹配均实际握手失败，HTTP/分享计数0；正确CA与SAN通过 |
| TLS策略/日志 | CERT_NONE/关闭主机名检查及运行前context漂移被拒绝；启用合成keylog context在联网前拒绝 |
| 实际跨域与HTTP重定向 | TLS流返回跨域SSE endpoint、GET302、share307，均不跟随；后者只创建一次且未知，不重试 |
| 真实MIME/响应头 | 错MIME和重复Content-Type不能进入协议，无POST |
| 实际超时 | TLS握手停顿、GET头空闲、SSE读取空闲触发socket timeout；每30ms滴送头字节没有空闲超时，却被约300ms总预算watchdog中断 |
| 真实关闭 | TLS reader确实阻塞时close，线程退出且再次close确认；记录首轮确认及本次耗时，不推导远端停止 |
| 断流/绑定 | peer在SSE半帧结束chunked流时拒绝；实际wire身份不符无分享 |
| 已受理后未知 | 测试服务先将合成share计数增1再不回ACK；客户端报timeout，持久未知，同Job新driver没有新请求 |
| 返回损坏 | 实际SSE返回非JSON share内容不验证、不重发，保留未知 |
| 外部门/范围 | 外部工厂和普通SSE构造器拒绝；任意目的URL拒绝；另一个TCP端口的内核探针得到EACCES |
| 输出/环境 | 合成HTTPS_PROXY/SSLKEYLOGFILE环境不改变driver路由/日志；结果、trace及持久状态不含合成链接/码/敏感异常文本 |

以上21个unittest方法中有多场景分支，使用真实本机TCP/TLS/HTTP和真实timer/线程，业务响应与副作用计数仍是合成。不是公网、百度服务器、账号权限、实际MCP SDK或真实网盘分享实测。初轮18项通过，扩展21项通过；最终针对结果标记和并发关闭确认的小改动后，干净预期提交副本21项再次全部通过，没有本轮失败记录。

## 隔离、可复现与证据

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_local_sse.py
```

runner只用已存在的OpenSSL生成两组**本轮合成临时证书/私钥**，然后建立一个自有回环监听端口。没有读取既有SSH/OAuth/网盘凭据、浏览器或真实配置，没有依赖安装/下载。临时密钥不打印、不提交，结束后清理本轮TemporaryDirectory；不承诺内存安全擦除。

这是新的、明确授权的本地I/O测试进程，没有放松旧禁网runner或修改系统安全配置。空HOME/配置、最小环境、-I -S -B、关闭额外FD；在启动服务线程前，为本进程和后续线程施加Landlock TCP bind/connect单端口规则，另端口探针实际EACCES。**此内核规则按TCP端口，不是IP防火墙，也不隔离UDP；应用另外硬绑定数值回环且不做DNS。没有文件系统沙箱。** 不把它称为完整恶意代码隔离。服务只绑定回环、不公开到LAN；只关闭本轮自有连接/服务/线程，不终止其他进程或清理旧资料。

独立副本只包含已跟踪文件及本轮文件；历史未提交四项未复制、未运行、未修改。未重复上一轮内存42项。源码/日志哈希、实际TLS/请求计数/停止耗时见[机器证据](validation/mcp-local-https-2026-11-10.json)与[日志](validation/mcp-local-https-2026-11-10.txt)。这些是本次本机测量，不是吞吐或硬实时保证。

## 剩余条件

候选驱动机械层已实现并有真实本地I/O证据；不能再把允许渠道缺失说成没有能力写本地驱动。**百度外部路由/凭据路径仍锁定，实际服务连接与认证/原对象/分享/领取均未尝试。** 下一步外部阶段仍需原控制允许依据、精确应用/原对象权限、实际业务返回/分享映射契约和逐次确认的短期凭据/私密返回范围；再审查外部IP/DNS固定、公共CA与代理/服务端日志、实际SSE兼容、真实请求超时及关闭行为。不能把本地注入改成任意主机或直接放开类型门，也不新建OAuth、自动刷新或重传样例。5GiB保留线、既有原上传及草稿PR状态不变。

## 2026-11-10 纠正与官方驱动开发进展

此前把 Mac 浏览器打开 `https://pan.baidu.com/` 的 Browser Use site safety gate 拒绝泛化为官方 MCP API 的前置封锁，依据不足，相关历史段落中的“先取得原控制允许依据/联系维护方”不再作为官方 API 开发或验证的通用前提。不能重试被拒网页或用另一浏览器/CDP完成同一被拒网页访问；官方 API 的具体请求若遇新的控制拒绝，停止该操作，不绕路。

新增 `OfficialHTTPSDriver` 和独立 `SSEClient.for_official_readonly`：固定官方 SSE 域名/443，只接受调用者显式传入的临时 access_token，不自动读文件、环境、浏览器或回调，不执行 OAuth/刷新。使用系统 CA、官方域名 SNI/主机校验与 TLS≥1.2；首次请求解析官方域名，拒绝非公共地址，单次会话固定一个地址，不自动切换重试。GET 仅向固定官方 SSE 路径提交 URL 编码令牌；后续消息仅允许同 origin 的受限 session endpoint，无跳转或代理、无 LLM。关闭时释放令牌引用，不宣称内存安全擦除。继承现有时限/watchdog/关闭及脱敏；目前错误码仍沿用部分 `mcp_local_*`，不据错误码判断网络范围。

此阶段允许协议握手/工具清单及 user_info/file_meta 调用；所有分享和其他工具在发包前拒绝。它是实际外部传输代码，不是已完成的真实分享适配器：尚未把真实身份、精确对象、服务响应与现有 Job 持久单次意图接线。现有 fixture 分享保护继续保持，不能直接把真实驱动塞入 fixture 工厂。

新增13项合成凭据检查在 seccomp 禁网 runner 通过；真实 socket/TLS 被 mock，不构成官方实网证据。因共享 GET 路径增加了 override，针对受影响的21项真实本地 TCP/TLS 测试回归通过，零失败/跳过；未重跑旧42项内存测试。官方 DNS/连接/认证/工具契约/身份/原对象/分享/领取均未尝试，没有读取真实凭据或重传样例。

DNS调用者等待有界，但系统解析线程不能强制取消，超时后可能短期继续运行；线程不持有驱动或令牌。系统 CA 加载与 DNS 环境是本机信任边界，不宣称隔离全部宿主配置。查询令牌会到官方服务，客户端不记录不代表官方服务端不记录。

下一步：从既有可信私有任务收据确定精确原对象/账号/应用和允许使用的凭据来源；明确一次临时读取/内存使用并向官方 SSE 提交的权限，不扫描秘密、不要求聊天贴令牌，不新建授权。确认该凭据兼容 MCP，取得实际只读响应再实现真实身份/对象 decoder 和持久单次分享接线；未知结果不重发。用户分享意图已明确，无需再泛问是否想分享。
