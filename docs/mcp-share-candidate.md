# 官方 MCP 分享：无凭据候选适配及真实建链进入条件

2026-11-09。`fast_transfer/mcp_share.py` 现在提供固定合成任务的分享参数、内部观察校验和一次创建演练；**不是 MCP 客户端、服务器连接、真实信封解码器或身份认证器**。现有 Go adapter 针对 PCS-Go Cookie 候选，不是同一个服务契约。本轮没有移植它的 errno/owner/shareid 形状，而是复用已有 Python Job 的锁、save 和 manual_review 状态，不建立新的工作流或通用分享账本。

## 来源、字段与未知项分级

固定来源为[百度 MCP README](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)，commit `b3983d330fea79c7b72e6b7014803e1830148d2c`、README Git blob `aebcff89265d8948be9e6dc7147cc2998b4e5d61`。版本与以下字段来自协调方已重新读取的公开资料；本轮复用该非敏感证据，没有下载或执行官方代码，也没有另称本地验证了完整 README 原文哈希。

| 层次 | 支持的内容 | 本轮如何处理 |
| --- | --- | --- |
| 官方文档声明 | user_info 输出 uk；file_meta 输入 fsids，list 输出 fsid/path/md5/size 等 | 校验内部合成观察，不构造尚未核实的这两个真实 RPC 请求，也不把 uk 自身当认证 |
| 官方文档声明 | file_sharelink_set 的 fsid_list 为字符串，内容是 JSON 字符串 ID 数组；period 默认7天，pwd 四位数字/小写字母 | 构造仅含 fsid_list/period/pwd 的私有参数候选；本轮只允许固定合成 ID 和7天，不声称其他期限不被平台支持 |
| 官方文档声明 | 返回 link/period/pwd/short_url | 本地候选严格要求四字段、期限/提取码与请求相同、URL 符合保守 allowlist；这是本项目验收政策，不是已证实的全部必填字段/返回类型 |
| 内部归一契约 | Observation.raw/status/app/session/task/account | 全部是明确的 fixture 元数据，不是 MCP 服务响应信封、可信 provenance 或权限票据；status=permission_denied 仅测试显式拒绝分支，不对应官方错误码 |
| 未证实 | 完整 MCP 成功/错误信封、字段类型/缺省语义、权限错误映射、分享 owner/shareid/精确对象映射 | 未实现真实 wire decoder；REST 的 errno/data、13998 及 Cookie 返回均不作为 MCP 成功或拒绝事实 |
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
3. **对具体单次方案逐次确认后执行**：以下是待补齐的候选审批边界，不是本次批准或已可执行配置。没有精确 endpoint/版本和凭据流向前，不请求笼统批准，更不收集秘密。

| 审批项目 | 已知最小候选范围与仍缺内容 |
| --- | --- |
| 执行主机/工具 | 仅原 dr-who-server 的 fast-transfer 隔离任务；不是 Mac。真实 MCP 客户端构建、服务器 endpoint/版本、SSE 或 stdio 方式及 TLS/日志边界尚未确定，均须明确后审查；现代码无法连接 |
| 凭据类别 | 仅官方确认兼容应用的短期 OAuth access_token 类别、受审单次内存 provider；具体允许的授予/访问方式待确认。不得找旧配置/环境/浏览器、传输 Cookie/BDUSS、client_secret 或 refresh token，不新增持久授权；不让用户在聊天贴令牌。任何敏感凭据操作须另有逐次确认，当前没有实施 |
| 对象/数据 | 原私有收据绑定的单文件 fs_id/path/账号/大小/双哈希，不换应用、不迁移/复制/上传、不枚举全盘/历史分享；只向已确认的官方服务提供建链必需参数 |
| 分阶段调用 | 先最多一次 user_info 与一次精确 file_meta 工具读取；来源/namespace/应用/对象证据不够即停止。创建阶段最多一次 file_sharelink_set；结果未知不重发。此为工具调用候选上限，不是 MCP 握手/网络请求总数契约；完整协议和映射核验工具/范围尚未知，不能现在执行 |
| 时限/分享策略 | 候选单次进程观察窗≤5分钟、分享7天、四位小写字母/数字码；不是已验证硬停止保证或全部平台期限支持。阻塞/超时按未知保留，不继续写入 |
| 返回 | 链接/提取码只回当前用户的明确私密渠道，不发客户/Slack、不进仓库/Wiki/日志；未核对分享与对象/权限映射时仅标未验证。具体私密返回途径仍需审阅 |
| 退出/保留 | 结束单次进程与客户端，释放内存引用，不宣称安全擦除；原文件/原授权/未知对象均保留。无秘密的意图/结果引用保留供核查；不删旧资料、不刷新/撤销原授权、不盲目取消未知分享。当前 README 未给本次分享可识别/撤销的完整契约，不能承诺自动清理；若需撤销必须明确仅本次新增对象和实际支持方法 |

本轮实际完成的是无凭据候选和必要测试；上述真实动作均为 **未尝试/pending**。下一优先动作仍是取得原控制允许依据并确认服务契约，不能用 fixture 校验或现有上传成功补齐。
