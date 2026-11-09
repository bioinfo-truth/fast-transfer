# M4.3/M4.4：可信身份、指定对象与分享的接入契约候选

当前状态：固定安全补丁可完整构建、已有请求层七项/配置拒绝门两项受限运行证据；**没有真实登录/分享实现接线，默认身份门不变**。本方案不是账户操作许可，不请求或接收真实秘密，不通过其他客户端绕过既有百度站点拒绝。

## 固定源码证明的调用链

依据均为 `qjfoidnh/BaiduPCS-Go` v4.0.2 commit `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`，不能推广为官方 API 支持契约或服务当前接受证据。

| 阶段 | 实际源码/字段 | 接入边界 |
| --- | --- | --- |
| CLI 登录 | main login → SetupUserByBDUSS → NewUserInfoByBDUSS → 贴吧检查/资料；可接受 BDUSS、STOKEN、完整 Cookie 或旧密码流程 | 补丁默认拒绝，保持关闭；不运行 CLI 登录，不导入 Xtransfer OAuth。 |
| Cookie 会话 | NewPCS 为内存 cookiejar 设置 BDUSS，SetStoken/完整 Cookie 是另外入口；app_id 是客户端参数 | 不是 Xtransfer 应用 OAuth，也不能因 app_id 相同就假设账号访问范围被限制到应用目录。实际最少需哪些 Cookie 尚未实测。 |
| 候选身份 | [PrepareUK](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/baidupcs/prepare.go#L100) GET HTTPS `/api/user/getinfo?need_selfinfo=1` → [UK](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/baidupcs/baidupcs.go#L474) → records[0].uk | 请求不需要贴吧资料返回，但尚缺官方公开 Cookie 契约和真实服务验证；不是已经建立可信身份。 |
| 身份命名空间 | 旧登录保存贴吧 Baidu.UID，SetUID 用于其他签名；UK 独立查询；CacheUK 以 BDUSS 作缓存键、可保留 24 小时 | 不沿用 CacheUK，不将贴吧 UID、Cookie UK、OAuth uk 仅凭名字互换。官方 [OAuth uinfo](https://pan.baidu.com/union/doc/基础网盘服务/获取用户信息/获取用户信息/)证明的是应用授权用户，不证明 Cookie 有效。 |
| 对象定位 | PrepareFilesDirectoriesList → `/api/list`，dir/order/desc/clienttype/num/page；CLI RunShareSet 先 matchPathByShellPattern，可能展开多个路径 | 新适配器只定位精确父目录/文件，不使用 shell glob、活跃账号全盘枚举或自动找同名文件。 |
| 建链 | [PrepareSharePSet](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/baidupcs/prepare.go#L740) POST HTTPS `/share/pset`，path_list/schannel=4/channel_list=[]/period/pwd/share_type=9 | 这是客户端 Cookie 路径，不等同于付费开放平台 `/apaas/1.0/share/set`。接口存在不证明商用资格或可跨应用访问。 |
| 解析与输出 | [ShareSet](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/baidupcs/share.go#L72) 判断 link 非空，将请求 Password 填回结果；CLI 输出链接/密码 | 不复用 CLI 的打印/随机密码兜底；需独立严格解析、私密返回和对象映射核验。 |

## 实际源码假响应验证：确认了哪些缺口

新增 `contracts/identity_share_characterization_test.go`，在实际 baidupcs 包中使用固定假 Cookie、内存 RoundTripper 和虚构样例路径，专用测试二进制在目标初始化前启用原 Landlock/seccomp 限制。初始化闭包是此前配置包已审查闭包的子集，无新依赖。**两个顶层特征测试、十二个子场景通过，含“确认不安全宽容行为”的场景，绝不是十二项安全条件通过或真实建链成功。**

- UK 缺少 errno 时仍接受单条正 uk；uk 为 0 或负数时也返回无错误。显式 -6、两条 records、uk 字符串类型则拒绝。
- ShareSet 对缺少 errno/shareid 的非空 link 仍接受，也接受 `javascript:` 假 link；空 link 或非零 errno 拒绝。
- 返回 Pwd 来自请求参数，不是服务器确认的密码或访问验证。测试还确认真实函数构造的 HTTPS 方法、路径、身份查询参数和分享表单字段；全部响应均来自内存，未发出百度请求。

默认 `go test -c ./baidupcs` 被上游已有 vet 诊断阻止：PrepareBDStoken 的 `string(pcs.appID)` 是单 rune 转换，不是十进制格式。该路径不在本次测试范围，未修改上游代码或锁文件；明确使用 `-vet=off -c` 编译特征测试后执行。故不能声称该包默认 vet 检查通过。日志与摘要见 `validation/pcs-identity-share-contract-2026-11-09.json` 和 `.txt`。

## 最小可实现的可注入适配器（尚未实现）

不删除全局 RequireVerifiedIdentityBinding，不接入普通 login 命令，不引入 JSON 开关开启真实访问。设计一个独立编排入口，依赖三个明确接口：IdentityAdapter、ObjectAdapter、ShareAdapter；默认工厂一律 unavailable，离线 fixture 实现不能构造真实交付资格。运行前还需与网络能力分离的允许渠道检查和具体人工授权记录，接口注入本身不算授权或密码学证明。

1. **VerifyIdentity**：同一短期进程内 Cookie 会话经允许渠道与严格 TLS 发出固定身份请求；限制响应大小/时限，拒绝重定向、重复 JSON 键、缺失/非整数 errno、非零业务码、非数组/多条 records、非整数/非正值 uk、额外尾随正文和解析未知。证书/传输失败、过期与响应未知分别记安全状态，不把它们映射成成功。
2. **BindPrincipal**：只有上一步真实响应有效，且与独立可信的预期账号证据精确核对，才得到带 namespace=`cookie_netdisk_uk`、会话引用、对象范围、校验时刻和短 TTL 的 Principal。预期证据不能只从同一未验证响应回填；OAuth 身份可作为已有人工核对背景，但必须确认命名空间/账号映射，不能自动认定等价。错配、身份未知、超时或换会话全部停止；不填默认 UID，不依赖贴吧昵称。
3. **ResolveExactObject**：仅列明确授权的精确父目录，限制分页；匹配既有样例的 path、fs_id、isdir、字节数和原收据引用，确认 owner Principal 与对象映射。分页无法确定、同名/改名/ID 漂移或摘要语义不明即停止。读取验证是权限证明的一部分，不能以同账号或旧 fs_id 推定当前 Cookie 会话可访问 Xtransfer 对象。
4. **CreateShareOnce**：必须持有同一账号/会话、未过期的 Principal 和对象证据，以及单独的建链授权。仅一个精确文件 path_list、有限期（候选 7 天）、四位小写字母/数字提取码；禁止随机兜底、永久链接或附加下载权益。发出前记录无秘密的独占意图，最多一次 POST。响应必须显式成功、正 shareid、受允许 HTTPS 百度分享 URL、无 userinfo/异常端口或重定向，不将请求密码回填冒充验证。
5. **VerifyShareBinding**：需要服务端能够核对 shareid→owner/精确 fs_id 集合/有效期/受控访问状态的证据。若当前客户端接口无法提供，保持 `created_unverified`，不标 delivered。按路径建链存在 TOCTOU，前后查路径不能声称原子绑定；必须承认并核查实际分享内容。客户端源码中的 share record/list 或 surlinfo 是研究候选，不保证具备全部证据，也不默认授权读取历史分享。

身份请求和资料查询完全分离：只有可信 Principal 已建立，资料可选且可失败；未知身份绝不因资料缺失降级为成功。当前没有生产适配器，不会把源码的宽容 parser 直接接到此契约。

## 最小请求预算与未知结果

M4.3 候选最多为一次身份 GET + 一次精确父目录 listing（分页时按明确上限，不能笼统保证只需两次），必要时再对一个精确对象查元数据。无下载、上传、改名或新建目录，不重新放置样例。已有对象是 Xtransfer 应用区中已核验公开 NCBI 小文件，精确路径/ID只在私密范围核对，不写公开文档。

M4.4 另行候选为身份/对象新鲜度核对 + 一次分享 POST + 允许的精准分享映射/访问核验。成功数量、密码和期限以真实返回/核验为准。需要 STOKEN/额外 Cookie、其他 API 或读取历史分享才能继续时，停止并说明新增数据范围；不自动索取更多凭据。

超时/断连/解析异常在可能已发送后进入 `creation_unknown`，不重复创建或盲目换端点。只能在已批准的读范围内找本次候选映射，无法确定则人工核查。取消不是删除文件；仅对确认属于本次且身份/对象匹配的新增 shareid，并且已有取消许可时执行，未知或历史分享不动。取消失败也保留 unknown，不伪称撤销。任务重启/凭据到期不会自动恢复写入。

## 无持久化及日志范围

凭据由未来明确许可的内存 provider 提供，不发现/读取用户配置、浏览器数据库、CLI 参数、环境或 Xtransfer token，不获取密码/刷新令牌。建议单次进程最长 5 分钟作为候选边界：退出/取消/错配即停止，丢弃 jar/provider 引用，不刷新或持久登录；Python/Go 字符串与崩溃转储的内存擦除不能保证，需审查 core dump/调试/崩溃日志策略后再真实接线。

不使用原 CacheUK（raw BDUSS 缓存键）、Config.Save、CLI stdout 或 verbose。公开记录只保存固定错误码/匿名任务引用；未来若为防重需本地私有意图记录，只存对象/授权引用和状态，不存 Cookie、密码或工作链接。完整链接/提取码只在批准的私密交付渠道返回，不能通过 GitHub/Wiki/Slack 转发；未知结果时的私有 shareid/映射保存范围也需列明。内存凭据不等于账号权限缩小，Cookie 被误用/泄漏仍可能影响整个账户。

## 技术缺口与访问许可分别处理

- 技术：严格 parser/Principal 绑定、精确对象映射、单次意图/unknown 恢复、分享映射核验和凭据退出生命周期尚未实现。现有安全补丁只是默认拒绝和传输保护；客户端 Cookie 接口的当前支持及最小字段要求也未证实。
- 平台：正式开放平台分享 API 需要企业认证/购买/开通；Cookie 客户端不是可宣称免费或商用豁免的绕行。客户端接口的公开源码并非官方服务支持契约。
- 渠道：既有 pan.baidu.com 浏览器站点安全拒绝仍有效。不能因为源码有接口、用户说继续研究、同账号或换成 CLI/代理/OAuth就判定已获准账户访问。需要原安全控制/平台工具对具体拟用动作、端点和数据范围的可验证允许结果，或其明确说明原拒绝适用边界；我们不能自行改写该拒绝。无法确认允许渠道时状态为 `access_channel_blocked`，先停在方案阶段，**不要求粘贴 Cookie，也不试通账户接口**。

## 分阶段供审阅的许可候选（没有在此申请或执行）

| 阶段 | 精确拟议范围 | 风险/停止条件 |
| --- | --- | --- |
| 0：渠道确认 | 明确 dr-who-server 原 fast-transfer 隔离环境、固定受审构建/摘要，获得上述可验证的账户访问允许依据 | 没有依据就不接收凭据/发请求；不把用户同意当成绕过安全控制。 |
| 1：身份/对象只读 | 另行批准单次 ≤5 分钟内存 Cookie 会话，明确 BDUSS 及是否确需 STOKEN 的用途；仅身份查询和精确样例父目录/对象验证，预期账号及私密对象映射先核对 | Cookie 账号级权限、服务器接收账号/路径元数据的风险；无效、错配、缺字段、附加凭据/端点、超时或 TLS/跳转异常即停止。无磁盘凭据、新授权/刷新/全盘读取。 |
| 2：一次建链 | 阶段 1 成功后另行批准已有精确样例一次 POST，候选 7 天/四位提取码，以及明确列出的分享内容核验读取和私密结果返回 | 可能产生链接且请求未知；不自动重试，不发送客户或读取其他分享。所需映射证据拿不到就不标交付。 |
| 3：退出与保留/撤销 | provider/jar 清理、进程停止、私有意图/结果保留期限；若要取消，仅批准本次确认新增 shareid | 内存清零不能保证，未知链接保留人工核查；不删除原样例、原授权或历史分享。 |

确定结论：可以设计一条不依赖贴吧资料的 Cookie 身份→精确对象→一次分享编排，但**现有实现还不满足可信身份/交付契约，且没有账户访问放行依据**。目前最小下一步是审查本契约及实现缺口；在允许渠道和具体阶段范围确定前，不推进真实认证。无需用户提供真实秘密来完成这一步。
