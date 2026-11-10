# 官方 MCP 分享：无凭据候选适配及真实建链进入条件

2026-11-09。`fast_transfer/mcp_share.py` 现在提供固定合成任务的分享参数、内部观察校验和一次创建演练；**不是 MCP 客户端、服务器连接、真实信封解码器或身份认证器**。现有 Go adapter 针对 PCS-Go Cookie 候选，不是同一个服务契约。本轮没有移植它的 errno/owner/shareid 形状，而是复用已有 Python Job 的锁、save 和 manual_review 状态，不建立新的工作流或通用分享账本。

当前补充：2026-11-10已接入[确定性 SSE/JSON-RPC 字节协议层](mcp-sse-protocol.md)，仅执行内存流；标准握手/信封已按固定 SDK 源码实现验证，真实 driver 和百度业务包装/来源认证仍未实现。下述17/38项保留为初轮候选结果，本次新增协议17项与必要回归42项另有证据。

## 来源、字段与未知项分级

固定来源为[百度 MCP README](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)，commit `b3983d330fea79c7b72e6b7014803e1830148d2c`、README Git blob `aebcff89265d8948be9e6dc7147cc2998b4e5d61`。上一轮版本与以下字段来自协调方已重新读取的公开资料，当时未下载或执行官方代码。后续静态审查已独立读取下节六份固定公开文件并核对 Git blob/SHA-256；始终未执行官方代码或访问账户。

| 层次 | 支持的内容 | 本轮如何处理 |
| --- | --- | --- |
| 官方文档声明 | user_info 输出 uk；file_meta 输入 fsids，list 输出 fsid/path/md5/size 等 | 校验内部合成观察，不构造尚未核实的这两个真实 RPC 请求，也不把 uk 自身当认证 |
| 官方文档声明 | file_sharelink_set 的 fsid_list 为字符串，内容是 JSON 字符串 ID 数组；period 默认7天，pwd 四位数字/小写字母 | 构造仅含 fsid_list/period/pwd 的私有参数候选；本轮只允许固定合成 ID 和7天，不声称其他期限不被平台支持 |
| 官方文档声明 | 返回 link/period/pwd/short_url | 本地候选严格要求四字段、期限/提取码与请求相同、URL 符合保守 allowlist；这是本项目验收政策，不是已证实的全部必填字段/返回类型 |
| 内部归一契约 | Observation.raw/status/app/session/task/account | 全部是明确的 fixture 元数据，不是 MCP 服务响应信封、可信 provenance 或权限票据；status=permission_denied 仅测试显式拒绝分支，不对应官方错误码 |
| 未证实 | 百度服务真实业务包装、字段类型/缺省语义、权限错误映射、分享 owner/shareid/精确对象映射 | 标准 JSON-RPC/CallToolResult 本地协议解码已实现；不假设百度业务包装，REST errno/data、13998 及 Cookie 返回均不嫁接为 MCP 事实 |
| 未证实 | 当前账号正式分享资格、现有 Xtransfer token/对象与 MCP 应用兼容性、跨应用范围 | 不探测、不迁移、不重新上传；个人体验应用独立 OAuth、仅测试且不得正式使用，不能借同账号推定互通 |

## 候选实现及防重、隐私

- 只接受精确 FixtureTransport 和 Observation 类型，以及 `job-mcp-fixture` 中16字节固定合成内容的既有模拟验证结果。应用/会话/账号/任务引用、对象 ID/path/MD5/长度逐项核对；这些硬编码 fixture 不是实际账户预期身份或 Xtransfer AppID。任何 caller scope/true 都不能开启 live；`live_connect()` 始终拒绝。
- 参数输出仅三字段；fsid_list 值如 `["2001"]`，外层是字符串，数组元素也是字符串。没有 token、AppID、Cookie、schannel、expired_type、额外 endpoint 或身份参数。ShareArguments 默认 repr 隐藏值，只有显式 fixture_arguments() 才导出含提取码的私有参数；这不是安全擦除或任意反射保密保证。
- 使用原 Job 锁读取/绑定，在模拟创建前先把原状态存成 manual_review / verify_share / mutation_outcome_unknown。保存失败不 dispatch；实际代码没有循环、重置或自动重试。创建超时、畸形响应或拒绝都保留原意图，同 Job 换 transport 或进程也不能再次创建。重开被拒绝时也保留前次 unknown 标志，不把“本次未创建”当作“前次结果已知”。复用 M5 的同锁 inode/可信本机操作者假设；新建另一 job 或恶意改状态不在防重保证内，不能推导远端 exactly-once。
- 返回只含固定状态/原因与 false 资格；不返回或落盘 link/short_url/pwd/原始异常。不向现有 Job 增加分享秘密字段，不打印 transport/observation/参数内容；它们默认 repr 为私有占位。显式导出参数或读取对象内部值仍是调用者责任，未引入真实凭据 provider。
- 字段全部合格仍为 candidate_unverified / mcp_share_mapping_unproven；mapping_verified、live_authenticated、share_eligible、delivery_eligible 始终 false。结果未知保守保留，即使内部 fixture 返回 permission_denied，也不能把这种模拟状态解释为已收到真实业务拒绝或确认无远端副作用。

## 测试与复现

新增 **17 项**测试；干净预期提交副本（原跟踪文件加本轮文件，排除历史未提交四项）中，受影响必要回归 **38 项通过，零失败、错误、跳过**。初次新增17项亦通过，无本轮失败记录。范围包括：

| 范围 | 实际检查 |
| --- | --- |
| 最小参数 | 三字段/双重字符串 ID、默认7天、提取码格式、坏类型及额外凭据字段拒绝 |
| 前置绑定 | 身份缺失/不匹配、应用/会话/账号/任务漂移、对象 fsid/path/大小/MD5 漂移/重复，均无创建 |
| 返回/拒绝 | 内部显式权限拒绝、未知 status、REST/Cookie/MCP-like 未确认信封、缺字段、坏类型、期限/码不符、非法 URL、返回 provenance 漂移 |
| JSON/隐私 | 重复键、编码/大小/深度/NaN 拒绝；结果、状态、repr 与输出不含合成链接/提取码/原异常 |
| 意图 | 创建前保存失败不调用；创建后注入 TimeoutError，新建真实子进程重开同 Job，创建调用为0 |
| 关闭门 | 非 fixture/custom/subclass transport 拒绝；live_connect 始终拒绝；合格响应也不获得真实资格 |

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_mcp_share test_workflow test_workflow_process
```

沿用受审 runner 的内核 seccomp 禁网并继承到重开子进程，实际 socket=EPERM；显式空 HOME/配置目录、最小环境、`-I -S -B`、DEVNULL stdin、关闭额外 FD。fixture 分享超时为注入异常，不是网络或服务器 timeout 实测。没有文件系统沙箱；路径由受审代码与本轮 TemporaryDirectory 约束，不隐藏宿主文件。没有连接 SSE/stdio、启动服务、读取账户或凭据、安装依赖。未重跑 Cookie/Go 模型、监督器工程或 M6。代码摘要和执行输出见[机器证据](validation/mcp-share-candidate-2026-11-09.json)及[日志](validation/mcp-share-candidate-2026-11-09.txt)。

## 用户“试一下创建分享”：当前能执行到哪里

用户分享意图已明确，目标仍是原 Xtransfer 应用区的那一份已完整回读验证 NCBI 样例。既有[真实样例记录](mvp-live-sample.md)与[机器收据](validation/mvp-live-sample-2026-11-08.json)表明：1,379,902 字节，MD5 `c13d459b5caa702ff7e1f26fe44b8ad7`，SHA-256 `a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255`；当时获准 Xtransfer access_token 临时内存使用、精确样例完整性通过后可建链，不包括新 OAuth/refresh token/Cookie/应用密钥、服务购买或其他接收人。上传/回读已通过，分享请求至今未发出；本轮未访问 VPS 或凭据，未核对当前云端是否变化。真实 path/fs_id/账号引用沿用私有收据，不进入公开文档，不由16字节 fixture 替代。

**本次没有执行真实创建。** 当前阻碍是尚无可验证的允许通道，以及 MCP 服务/响应/对象范围依据和真实适配实现缺失，不是这次百度 API 已拒绝。Browser Use site safety gate 拒绝的是 Mac Chrome 通过 cua.createBrowserTab 观察 `https://pan.baidu.com/`，明确禁止其他浏览器、间接执行、CDP 等实现同一被拒目的；不能借 MCP 官方存在、换主机或用户“试一下”绕行。规则 ID、维护方及正式复核路径仍未知；也不能把该拒绝扩大成所有百度 API 被禁。

到一次真实建链的最少顺序是：

1. **先有允许通道依据**：原 Browser Use site safety gate 维护方/管理者对该受阻目的提供正式范围/允许复核结果，以及拟用通道自身允许依据；本轮未联系或尝试放行。不是泛泛再问用户是否要分享。
2. **确认服务及技术范围**：由百度确认当前 MCP 应用是否获准为既有 Xtransfer 精确对象建链、测试/正式用途边界及所需凭据类别；取得完整成功/权限拒绝信封和可核实的身份/应用/对象/分享映射依据。不能拿体验应用 token 试探或复制对象求通；缺失映射时不能报 verified/delivered。然后才实现并审查真实 transport/decoder 与私密交付接线。
3. **对具体单次方案逐次确认后执行**：以下是待补齐的候选审批边界，不是本次批准或已可执行配置。现在已从固定公开配置确认 SSE endpoint；实际服务运行版本、客户端构建及凭据/日志流向仍需审阅，不请求笼统批准，更不收集秘密。

| 审批项目 | 已知最小候选范围与仍缺内容 |
| --- | --- |
| 执行主机/工具 | 仅原 dr-who-server 的 fast-transfer 隔离任务；不是 Mac。已确认官方公开 SSE 入口为 `https://mcp-pan.baidu.com/sse`，查询参数认证；真实客户端构建、服务运行版本及 TLS/日志边界仍未确认。stdio 示例仅上传，不能当作分享服务；现代码无法连接 |
| 凭据类别 | 仅官方确认兼容应用的短期 OAuth access_token 类别、受审单次内存 provider；具体允许的授予/访问方式待确认。不得找旧配置/环境/浏览器、传输 Cookie/BDUSS、client_secret 或 refresh token，不新增持久授权；不让用户在聊天贴令牌。任何敏感凭据操作须另有逐次确认，当前没有实施 |
| 对象/数据 | 原私有收据绑定的单文件 fs_id/path/账号/大小/双哈希，不换应用、不迁移/复制/上传、不枚举全盘/历史分享；只向已确认的官方服务提供建链必需参数 |
| 分阶段调用 | 先最多一次 user_info 与一次精确 file_meta 工具读取；来源/namespace/应用/对象证据不够即停止。创建阶段最多一次 file_sharelink_set；结果未知不重发。此为工具调用候选上限，不是 MCP 握手/网络请求总数契约；完整协议和映射核验工具/范围尚未知，不能现在执行 |
| 时限/分享策略 | 候选单次进程观察窗≤5分钟、分享7天、四位小写字母/数字码；不是已验证硬停止保证或全部平台期限支持。阻塞/超时按未知保留，不继续写入 |
| 返回 | 链接/提取码只回当前用户的明确私密渠道，不发客户/Slack、不进仓库/Wiki/日志；未核对分享与对象/权限映射时仅标未验证。具体私密返回途径仍需审阅 |
| 退出/保留 | 结束单次进程与客户端，释放内存引用，不宣称安全擦除；原文件/原授权/未知对象均保留。无秘密的意图/结果引用保留供核查；不删旧资料、不刷新/撤销原授权、不盲目取消未知分享。当前 README 未给本次分享可识别/撤销的完整契约，不能承诺自动清理；若需撤销必须明确仅本次新增对象和实际支持方法 |

本轮实际完成的是无凭据候选和必要测试；上述真实动作均为 **未尝试/pending**。下一优先动作仍是取得原控制允许依据并确认服务契约，不能用 fixture 校验或现有上传成功补齐。


## 实际入口与授权流静态审查（2026-11-09）

本节为新增公开源码审查，**没有代码修改，没有重跑17/38项测试**。仅通过 GitHub 公共只读接口取得固定提交的六份文件，校验返回 Git blob 与本地内容 SHA-256；用 AST/文本检查，未导入、安装或执行它们。复核既有上传记录只读仓库脱敏文档，不查 VPS、环境值、浏览器、账户或含令牌配置。文件清单/摘要及审查断言见[静态证据](validation/mcp-access-static-2026-11-09.json)。

### 已确认的数据流与不能推导的事实

1. [servers_config.json](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/client_demo/servers_config.json)及[README 接入配置](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md#L375)给出 `https://mcp-pan.baidu.com/sse`，用 `access_token` 查询参数认证。此为源码声明的 SSE 入口，不是本次连通性/服务版本实测，也不是允许当前账户访问的依据。
2. [Server.initialize](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/client_demo/client_demo_sse.py#L77)依次 sse_client→ClientSession→initialize→list_tools；实际工具前还有会话初始化/能力发现，不能把一次 user_info、file_meta、file_sharelink_set 写成总共三个 HTTP 请求。SDK 的连接、重连、消息 endpoint 和超时策略本次未审到可用于账户的程度。
3. [个人体验说明](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md#L317)仍是独立 OAuth 体验、仅测试且不得正式使用。旧上传成功只证明当时获准样例路径有效；**当前 token 是否存在/未过期、当前 scope、账号/AppID 绑定、MCP/分享权益及跨应用访问均无法从这次无凭据检查确认**。没有用真实 token 请求或读取其存储；不能把历史有效写成现在有效，也不自动刷新或申请新授权。
4. [子目录说明](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/README.md#L1)把 stdio fileupload_tool.py 定位为上传工具；[实际注册函数](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/fileupload_tool.py#L57)是 upload_file，其 get_help 为资源。公开未截断树中没有独立的本地分享工具入口；安装这个上传入口不能被称为具备本地 file_sharelink_set 实现，不以另一个仓库/远端服务的可能能力填补这里。

### 原 demo 为什么不能原样使用

| 源码位置 | 静态发现 | 本任务所需边界 |
| --- | --- | --- |
| 配置初始化 24–32、main 417–427 | 读取 LLM_API_KEY、load_dotenv 和磁盘 servers_config.json | 不运行该路径；不读取 .env/现有配置，不填 token 到 demo 配置，不新增千帆密钥或持久授权 |
| [LLMClient.get_response 216–267](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/client_demo/client_demo_sse.py#L216) | 将 messages 发往千帆 chat/completions，模型字段为 deepseek-v3 | 未来只能确定性直调明确工具，无千帆或其他 LLM，无原话、工具结果、链接外发 |
| ChatSession 288–339、379–406 | 记录工具 arguments；把输入及工具结果放入 messages，再调用 LLM，并记录回复/错误细节 | 不复用该会话循环/日志；只允许非秘密固定原因/匿名指纹，禁止原始工具返回、URL、分享链接/提取码或异常串 |
| [Server.execute_tool 120–163](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/client_demo/client_demo_sse.py#L120) | 默认 retries=2，while attempt<retries，即异常时至多两次尝试 | 创建分享至多一次；HTTP/RPC/SDK各层均不得自动重发有副作用调用，超时或失联保留未知，不能仅改上层循环后宣称已消除 SDK 重放 |
| sse_client(server_url) 与原始异常输出 | demo 没有本项目已审的日志/跳转/目的端与凭据流向保护 | 不推断 SDK 不验 TLS，但也不把默认库行为当已审保护；先确定锁定版本，再审 TLS/主机、重定向、SSE 后续消息 endpoint、代理环境及 debug/error 日志 |

**查询参数认证的取舍必须说清：** 官方示例要求 token 进入 SSE URL；“不暴露 token”只能要求它不进入 argv、工具 arguments、可见输出、追踪、配置、异常或客户端日志，不等于 token 从未进入 URL/官方服务。未来若获准，只能在受审短期内存通道向该官方端点提交；TLS 正常验证、跳转默认拒绝、后续 endpoint 不得任意跨主机传递认证。服务端/代理是否记录查询仍需官方和具体客户端部署策略确认，本机脱敏不能控制远端日志。**尚无不把 token 放 URL 的受支持方式证据**，不能擅自换成 Authorization header 后说兼容；若该数据流不可接受，这条 SSE 方案不能开始。当前没有构造或发送任何含真实 token 的 URL。

### 现有环境可复用到哪一步

已确认本项目 Python 为3.14.4。官方 [pyproject](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/pyproject.toml)声明 Python≥3.12及依赖范围约束；**官方仓库同时存在 [uv.lock](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/uv.lock)**，不能据 pyproject 的下界写成官方无锁。2026-11-10已独立读取固定锁文件：96,472字节，Git blob `a792c3d7eb17925a76e82af04d94050ef290fe1b`，version=1/revision=1、requires-python≥3.12；锁定 mcp 1.6.0、httpx 0.28.1、python-dotenv 1.1.0、aiohttp 3.11.16等，列有 PyPI 来源和制品 SHA-256。这里只核对锁文件及其声明，未下载制品验证其哈希，也未完整审查依赖闭包。

**本项目尚未采用或完整审查该锁，没有跟踪的 MCP 依赖锁或真实 SSE 连接器**；未安装、导入、验证 dr-who-server Python3.14下的依赖/协议兼容或客户端运行时。锁文件存在与最低 Python 范围不等于已有可执行的受审客户端，mcp_share.live_connect 仍直接拒绝。原静态证据中的 official_dependencies_locked=false 已更正，并保留此次纠错说明；其余 SSE、LLM、日志、重试和真实阶段阻碍结论不变。

可复用的是已审 fixture 字段/隐私校验、Job 锁/持久意图、默认关闭的真实门及脱敏/停止的设计；禁网 runner 只用于离线测试，不能充当联网 MCP 客户端。现有 PinnedBaiduHTTPClient 的 REST 允许列表/流接口也不是 SSE/MCP 传输，不能把主机加入允许列表就宣称已有完整安全会话。现有代码没有一条可直接安全建链的真实 MCP 路径；本轮不为填补它新增未经允许的依赖或客户端。

### 公开问题单的证据级别

- [issue #1](https://github.com/baidu-netdisk/mcp/issues/1)：个人授权链接失效的用户报告，2025-08-04创建，仍 open，最后更新2026-04-28；两条评论 author_association 均 NONE，没有维护者确认。不能据此断言当前授权失效或已修复。
- [issue #2](https://github.com/baidu-netdisk/mcp/issues/2)：2026-05-21的 SSE/Streamable HTTP 405 差异用户报告，作者 NONE、无评论。只是协议配置风险，不是官方支持矩阵、服务可用性或本账号证据；没有执行其中命令或连接入口。
- 协调方的插件目录搜索未找到匹配项，仅说明该次目录查询无返回，不证明目录外无插件；本轮未再安装/搜寻替代通道，也不以插件绕过既有拒绝。

### 真实阶段的具体候选顺序与第一阻碍

**第一阻碍仍是 Browser Use site safety gate 对原受阻目的的允许依据缺失。** 已知 SSE endpoint 并不解决它。本次能请求的最小具体动作，是请能处理原控制的维护方/管理者提供对“由 dr-who-server 对上述官方 SSE 服务执行原精确样例只读核验及单次建链”这一目的的适用范围/正式复核决定；控制的维护方身份、规则 ID和途径仍未知，本轮没有代为联系。单凭用户再给一个 yes 不能改变该控制；分享意图已经明确，无需再次询问要不要分享。

假设允许通道成立，仍须先完成客户端/SDK锁定及静态审查、成功/拒绝信封和应用/对象/映射契约确认，然后逐次审阅以下实际动作；这些不是当前许可：

1. **秘密操作的单独确认**：主机仅原 dr-who-server、经审查的固定构建；仅单次临时使用已确认兼容的短期 OAuth access_token。要明确凭据由谁通过哪个受审内存 provider 交付、向哪个官方端点提交及 URL认证风险。不得先从环境、旧文件、浏览器或 VPS找 token，不导出/传输高度敏感凭据；client_secret/refresh token/Cookie不在范围内，不新增/扩大持久授权。若现有 token 已过期或不兼容，停止而非自动授权/刷新。
2. **会话与只读阶段**：明确允许 SSE连接、ClientSession initialize/list_tools 等必要协议流量与非秘密 schema 处理，再至多调用一次 user_info、一次仅原私有收据 fs_id 的 file_meta；不枚举网盘、历史分享或其他应用。核对独立预期账号证据、当前应用/会话 provenance、精确原文件 path/fsid/大小/摘要，来源/语义不足即停。工具数不是底层请求数，SSE/SDK重连不能成为隐式重试。
3. **一次创建阶段另行确认**：仅同一已核对象，一次 file_sharelink_set，7天/四位数字小写字母提取码；不上传、迁移、复制或扩大对象范围。先持久意图，禁止自动重发；失联/解析失败保持未知。缺少可审的分享→账号/对象/期限映射来源时，不把返回 URL 当 verified/delivered，更不能用同账号或手填 owner 补证。
4. **返回与退出**：链接/码仅回当前用户经审阅的私密途径；不进入 LLM、公共仓库、Wiki、Slack、异常/日志。结束会话与客户端，释放引用、不承诺安全擦除；保留原上传/授权及未知结果，不删资料、不自动撤销/重建分享。若需领取验收，还要明确允许的中国境内接收主机/人员、链接/提取码私密使用和下载/双哈希范围；这不包含在本次静态审查或现有 M6 本地工具验证中。

当前实际状态：公开源码静态审查 **完成**；真实 SSE 连接、token 校验、user_info/file_meta/file_sharelink_set、领取均 **未尝试/pending**。不是已被百度业务拒绝，也不是结果不明的真实调用；没有发生需要查询补偿的分享操作。
