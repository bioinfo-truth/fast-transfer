# 现有 Xtransfer 应用的官方设备码路线

> 当前目标更正：MCP须在海外业务VPS验收。停止沿用开发主机的授权命令；先核查现有授权和VPS部署，见[业务VPS前置](business-vps-preflight.md)。两次用户报告未标主机，不能定位。

2026-11-10：按用户纠正，使用**现有、自有Xtransfer应用**，不借用个人体验应用/共享AppID、不另建应用。用户描述的开发者主体状态没有在控制台核验；“只有一个应用”不能证明当前grant_type、scope、MCP或分享服务权限有效。本轮未读AppKey/SecretKey/token、未请求真实device_code、未启动OAuth/刷新、未访问被拒网页、未部署VPS或迁移原对象。

## 官方依据及能确认到哪里

- [官方Go SDK DeviceCode](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/baidudriver/api/auth_device_code.go)固定 `GET https://openapi.baidu.com/oauth/2.0/device/code`，参数 `response_type=device_code`、`client_id=本应用AppKey`、`scope=basic,netdisk`；[DeviceToken](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/baidudriver/api/auth_device_token.go)固定 `/oauth/2.0/token`，`grant_type=device_token`、`code=设备码`、同一client_id及client_secret。这是协议/接口证据，不是Xtransfer当前服务资格实测。
- [官方MCP仓库生成API](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/openapi_client/api/auth_api.py)确认相同GET/查询参数并带 `openapi=xpansdk`；响应模型列device_code/user_code/verification_url/expires_in/interval及access_token/expires_in/scope/**refresh_token/session字段**。[设备令牌模型](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/src/baidu-netdisk/openapi_client/model/oauth_token_device_token_response.py)意味着不能保证服务器只签发短期token；本程序只不保存/使用其他凭据，完整JSON响应仍会短暂进入进程。
- [百度OAuth错误表](https://openauth.baidu.com/doc/appendix.html)明确authorization_pending、authorization_declined、slow_down、unauthorized_client/invalid_scope等含义，以及轮询间隔须大于5秒。本地策略保守取至少6秒、slow_down再加5秒；加5和本地次数/时限是本项目策略，不冒称百度承诺。
- 旧developer wiki地址经读取返回问答内容，未取得设备码文档，未作为当前契约。没有照搬个人体验应用链接、千帆/LLM示例、关闭TLS或输出原始响应的脚本。官方源仅静态读取，未安装或执行SDK；5份固定源码及哈希在证据中。

## 已有与新增安全组件

原项目已有本人无回显TTY输入、官方MCP只读/发现入口、显式原对象期望以及Job持久单次意图；此前受控代码中无设备码接线或明确可安全读取的AppKey/SecretKey来源。本轮不扫描旧配置，新入口要求用户本人隐藏输入。

新增 `DeviceOAuthHTTP`（固定openapi域名/443、系统CA/主机验证、DNS公共地址和会话内固定、GET参数允许列表、无代理/跳转/自动重试、15秒单请求/3秒I/O、16KiB响应上界、关闭确认）、`DeviceFlow`（单次申请、受控轮询、私密user_code、一次性token lease）及 `xtransfer_device_authorize.py` 终端入口。失败/原始异常/URL/密钥/设备码/token不进入普通输出、argv、环境、.env、历史、日志、公共文件或LLM。

SDK用GET查询传SecretKey，本实现不能把它说成只进POST正文；服务端/中间设施日志风险不由客户端脱敏控制。请求scope是应用级basic/netdisk，**不能在OAuth服务端缩成仅原单文件**；后续本地工具权限控制是另一层。用户页面同意会创建/更新服务端授权，可能签发refresh token并在进程退出后持续有效。程序不自动撤销、刷新或声称退出即使服务端token失效，不保证内存安全擦除。

## 历史终端流程说明（当前不要重做授权）

代码仅当前项目主机评审工作区就绪，已核实 `/usr/bin/python3` 为3.14.4且入口 `--help` 可运行。**原海外VPS没有部署此入口**；若必须在VPS操作，先明确部署位置/版本，不能直接假设已有同名路径。使用本人、不记录输入的前台交互终端；非TTY不回退到回显/stdin，复用输入窗口60秒及取消/EOF/信号恢复规则。

已撤下开发机上的可执行授权命令。用户已报告自行完成设备兑换；现优先确认VPS现有授权，不重复grant。待业务节点目录/版本及具体读取/请求范围明确后再提供该节点操作步骤。以下仅保留流程与安全边界，不作为现在执行指令。

1. 隐藏输入确认 `XTRANSFER-DEVICE-basic,netdisk`，再在AppKey提示中输入**已有Xtransfer这一项**的AppKey。程序最多发1次设备码请求；未知结果不重发。
2. 程序仅在私人控制TTY显示经校验的官方HTTPS verification_url及user_code，**不显示device_code**，不打印到普通报告或交给LLM，不自动开浏览器或抓取二维码。用户本人打开页面，核对确为Xtransfer、正确账号及期望权限后自己批准；如果页面应用不符或不接受scope就取消。只接受已审静态HTTPS openapi验证地址；若服务实际返回HTTP/其他路径，停止，不擅自改写或跳转绕行。
3. 本人确认页面批准后隐藏输入 `XTRANSFER-APPROVED`，再输入**同一应用**SecretKey。这样SecretKey不必在浏览器批准期间持有。协议轮询先等至少6秒，pending按间隔继续、slow_down加间隔；整个设备阶段受返回expires_in与本地300秒更早者约束，最多30次token轮询。300秒/expiry在请求前后和等待循环检查；单次在途HTTP另有15秒预算，不能宣称硬实时在300秒整中断，过期后的响应不用于交接。两步client_id保持同一内存AppKey。
4. 未知/混合错误与token响应、权限拒绝、过期、网络异常、关闭不确认或取消均停止；已兑换结果不可靠时保持unknown，不猜成功，也不盲重发poll或新device请求。取消/进程结束不等于撤销服务端pending或已批准grant；不要为补偿未知结果自动再跑。
5. 成功后仅保留内存access_token、实际scope及期限，不显示/持久化令牌，不使用refresh/session字段。scope不是精确basic/netdisk或信封未知即停止。令牌lease只能取用一次，过期拒绝。代码没有证明AppKey对应Xtransfer，报告application_binding_verified仍false，不以用户输入自证权限。
6. 另一次隐藏输入 `MCP-DISCOVER` 才会把该token交给固定官方MCP做最小工具发现；取消则只释放本地引用。不会直接读账号/文件或分享，不将设备授权成功当MCP兼容。后续账号和原对象核验仍需可信私有期望记录、可确认实际schema/应用范围；原文件保留，真实分享门及Job未知不重发保护不变。

当前最小缺口：用户本人能够取得同一Xtransfer AppKey/SecretKey并在自己终端输入、选定执行主机并明确接受scope/新grant风险、自己在官方页面核对批准；本轮没有索取/读取这些值，未证明该应用实际支持设备grant。只需个人终端动作，不需要发送密钥、代码或token到聊天。无法满足这些条件时停，不转个人测试应用、不新建OAuth替代路线或扩权。

## 本轮验证

干净副本新增 **24项设备码检查** + 复用终端 **23项**，共 **47项通过，零失败/跳过**。设备/OAuth网络全为mock，继承seccomp禁网；真实自有PTY部分仅验证合成输入，不读用户现有终端。覆盖同应用参数、query编码、公共DNS/TLS主机政策、禁止redirect/refresh、pending/slow-down/expiry/次数限制、未知申请/兑换和混合响应不重发、私密代码展示限制、scope拒绝、lease单次与过期、参数引用清理、关闭不确认、非交互命令拒绝，以及独立MCP交接动作。没有用这些结果冒称实网OAuth、账号或分享成功。

[源依据/策略/已测源码哈希](validation/xtransfer-device-2026-11-10.json)、[完整测试输出](validation/xtransfer-device-2026-11-10.txt)。

后续用户执行报告与静态跟进：[设备兑换返回成功、MCP tools/list本地校验失败](mcp-protocol-diagnostics.md)。已补诊断及标准_meta兼容，根因和官方互通尚未实测确认，本轮没有新授权或读取秘密。
