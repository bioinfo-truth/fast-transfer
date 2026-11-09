# 路线图与决策

## 2026-11-08：当前 MVP 执行范围

首版采用人工公开 HTTPS 链接或 manifest，不要求项目号解析、淘宝、支付或网站。按 M1 输入样例 → M2 下载/源校验 → M3 网盘上传/核验 → M4 受控分享 → M5 最小任务与失败处理 → M6 国内领取推进。已有工具实验保留，不重跑；跨 OpenList 服务重启的分片恢复不是当前前置门槛。

M1 与本地 M2 已有真实 NCBI 小样例及测试证据，新一轮上传/分享/客户领取未执行；实现处于评审分支，未部署。缺少大小、源站摘要或来源/分发审核则进入人工处理，不自动下载。真实上传和分享须分别核对新用途的授权，不能沿用已结束的临时凭据测试许可。详见 [MVP 范围与输入](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。

M2 补充状态：后端感知的同盘/分盘预算组件、未知开销拒绝和离线动态检查已完成；实际上传/回读过程的空间保护仍待 M3 联调，不能视为整个 M2 已验收。详见 [MVP 范围与输入](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。

M3 当前状态：单次获准真实 NCBI 小文件已完成上传及完整回读双哈希核验；初次解析失败后在原空目录安全续办。一般模拟入口不变，实际分享/境内领取及完整服务验收尚未完成，详见 [MVP 当前交付](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。

以下保留长期架构/早期路线，不表示这些阶段已经实现。


## 阶段 0：测试准备

确认洛杉矶 VPS 的可用性、年费及续费、持续流量规则和退款条件；准备百度网盘账号。建立测试记录，不存放密钥和客户信息。

## 阶段 1：端到端验证

从美国和欧洲公开数据源各选代表文件，分别测源站下载、直传网盘、分享和中国境内获取体验。测不同时间段的稳定性、总时长、实际流量及每 TB 成本。保留 AList 历史基线，后续适配基线改用 OpenList；以直接 OAuth 验证分片上传和恢复，BaiduPCS-Go 作为源码参考，不重复 Cookie 登录。

## 阶段 2：可靠传输

选择经测试的上传后端；完善文件级队列、磁盘预算、状态恢复、错误处理和校验。独立评估超出本地容量的单文件，以及百度网盘单文件和分片数量限制。

## 阶段 3：数据库插件

定义统一的项目、样本、文件解析契约；首个候选为 ENA，之后扩展 SRA 与 GEO。明确原始数据、处理结果、受控访问及格式转换的区别。

## 阶段 4：交易和交付

先人工录单与分享，验证数据范围、报价、保存期限及客户体验；再核实淘宝 API、支付状态、交付消息权限后自动化。

## 决策与待验证

- 美国节点优先；欧洲节点取决于实际数据源和链路结果。
- 首台测试 VPS 优先选择 Debian；具体版本以供应商提供的镜像及其安全支持状态为准。系统选型不预设能够改善跨境传输速度。
- 先直连网盘，回国代理仅在数据证明有必要且成本可接受时再引入。
- 以公开数据为首期服务范围；具体来源、转载和商业服务条款需核验。
- 优先使用个人开发者应用和官方 OAuth 进行小文件上传验证；先确认账号认证、应用与授权状态，再执行测试。上传成功、续传与自动分享分别验收。
- 百度分享、淘宝自动交付和收费服务的具体权限与规则待核实；正式分享服务的资格、费用及配额以官方审核和报价为准。

## 补充：组合路线

- 先测海外 VPS 直传网盘与离线 URL 拉取，包含真实数据、校验和失败结果；不依赖境内代理。
- 完成逐文件空间预算、失败恢复与网盘节点对照，确认实际链路后再接订单。
- 对超大文件分别验证双遍读取和独立分卷：比较本地峰值空间、源站请求量、流量费用、交付时间及客户合并体验。
- 当海外存储不足或作为性能对照时，测试境内主机加 NAS 路线；先核对软路由出口规则与原有代理额度。
- 保留原始结果，根据证据选择已验证路径；自动化策略和 SLA 不早于可靠性验证。

## 隔离不覆盖候选已实现（无真实调用）

新增 fake-only 候选：随机任务名配合本地持久独占目录，云端新目录 rtype=0，文件 precreate/create 一致 rtype=1；目录 fs_id/path 身份复核、返回改名即失败、会话过期/重放拒绝、提交未知不重试、保留全部原有及新增/不确定对象。查询不是无竞态原子性证明；此候选允许冲突时留下改名对象，不能声称零副本。源/远端长度、完整双哈希、空间及 stop 闸门继续复用。新增 7 项候选测试通过，真实写入仍独立关闭，模拟不获得交付资格。

保护原有资料可采用这一官方不覆盖策略候选，不再将 precreate=0 的严格零改名依据缺口作为全部工程阻碍。真实目录查询、权限/权益、节点行为和 M2/M3 联合验收仍 pending、未尝试；未来明确批准须包含新任务目录及可能改名/未知对象的保留范围，不覆盖、不删除、不分享。详见[候选实现、官方来源与残余风险](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-baidu-http.md)。

## M4/M5 本地独立部分（仍无真实动作）

已实现单任务离线编排：M1 输入指纹 → 已有 M2 源文件/收据复核 → M3 模拟及空间检查 → 人工分享回填/交付清单草稿。状态私有持久化、同任务锁、查看、重复启动拒绝，以及失败/取消/人工核查待办已补齐；中断或提交未知不会自动重试写入。不能从 JSON true 获得真实网络或交付权限。

官方帮助说明可设分享密码/有效期且分享可能被取消，但个人账号/应用实际分享资格仍未知。回填仅为未验证声明，保存文件映射、期限与链接/授权引用指纹，不保存链接原文、提取码或凭据；错映射、越界、过期均拒绝，模拟/真实交付资格始终隔离。没有创建或访问分享、发送给客户或重新下载数据。新增 8 项离线测试通过；真实 M3/M4 接线、实际建链/发送、完整恢复和 M6 国内领取仍待验收。详见[工作流、人工步骤与验收矩阵](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-workflow.md)。

## M6 验收准备完成，境内实测未执行

已补齐同一任务/文件映射/源版本/长度/MD5/SHA-256 绑定的期望、领取观察与本地回执契约，以及只读所选本地文件的核验工具和实际验收清单。上传回读、分享声明、领取地点/方式、耗时/流量/空间/人工步骤分开记录；只保存匿名指纹，禁止凭据、私有路径及链接密码。错误任务/映射、长度/双哈希、前序缺失/未知、时间倒序、重复 attempt 和模拟冒充真实均有离线检查。

新增 8 项合成小文件测试通过；工具不联网、不下载、不开分享、不发消息、不改原任务的交付状态。自填地点、证据指纹及 JSON true 均不证明境内位置/授权，任何输出都不自动标 delivered。当前没有明确境内设备/测试人、真实 M3/M4 证据或领取许可，M6 实测仍 pending、未尝试。后续所需设备/操作者、对象/接收范围/期限、领取方式及证据返回方式仅列为待确认清单，不在本轮再次申请 M3 授权。详见[验收准备、模板与边界](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-acceptance.md)。

## 单次获准真实样例：上传与完整回读通过

已有 1,379,902 字节 NCBI FASTA 在海外节点完成真实上传、远端身份/长度与完整回读 MD5/SHA-256 核验。首次节点响应解析失败后，确认原目录 ID/path/空列表及零分片/零提交，修复官方 error_code 信封并在同一目录新建预上传会话续办，没有复用旧 uploadid 或新建第二个云端目录。累计目录创建 1、预上传 2、分片 1、文件提交 1、完整回读 1；不覆盖/删除旧资料。

续办约 13.65 秒，采样最低空闲约 7.846 GiB，正常停止及凭据引用释放；无新访问令牌文件，原授权/源/对象保留。这只证明此小文件和正常空间/停止路径，不代表权益极限、大文件、真实中断或长期性能验收。普通入口仍模拟，未来任务无持续授权。

分享创建/访问验证仍 pending、未尝试，不是权限拒绝；官方新分享服务需企业认证及付费开通，用户已说明当前未开通，先用个人网盘正常客户端手动建链；未来 API 开通仅为备选，需企业认证和商务询价，无购买或授权变更。链接/提取码仅私密返回，不能将直链/内部路径作为分享交付。M6 境内领取仍未执行。详见[原始失败、续办和实测证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-live-sample.md)。

分享服务的官方开通步骤、商务入口及费用待确认项见[开通备选说明](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/baidu-share-service.md)。当前没有可用分享链接，建链后仍须私密回填并核验访问状态。

本轮分享自动操作已停止：原项目主机无可操作的已登录官方页面；协调方在用户 Mac 上访问百度网盘被浏览器站点安全策略拒绝。无链接，分享请求未发出，不绕过限制；用户可自行在官方客户端为精确样例建链。此限制与已成功的上传/回读分别记录。


## 2026-11-09：自动建链资料核对与候选

公开文档确认当前新接口为 `POST /apaas/1.0/share/set`，使用 `fsid_list`（JSON 字符串数组）、`period`（天数）、`pwd`（四位数字/小写字母），成功结果位于 `data`；不能直接采用外部资料的 `filemetashare`、`fid_list`、`expired_type` 或将令牌拼到 baidu.com 的代码。企业认证、服务购买/权限仍是正式接入条件；每日“几百次”及错误码 11000 的单一含义没有核实，不作为实现依据。

BaiduPCS-Go 指定版本源码有 `share set`，不是 `share create`；它使用客户端登录通道的 `/share/pset`，不能假设复用现有 OAuth 上传令牌。另发现百度官方 MCP README 列有 `file_sharelink_set`，但工具清单和个人限时体验不证明本应用具备分享权益，暂列候选，未安装、授权或调用。

当前仍由用户在官方客户端为精确样例手动建链并私密回填后核验；不恢复本轮自动分享或绕过此前浏览器安全拒绝。未来官方接入候选应加入任务/文件绑定、私有结果持久化及防重；未知创建结果先核查，不盲目重发。目录聚合交付可减少操作，但隔离/内容变化和平台支持仍待验证。详见[核对表、固定版本源码及候选边界](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/baidu-share-service.md)。


### 官方 bdpan 候选补充（仅公开文档核对）

用户当前目标仍是自动创建分享链接；手动建链只是交付备选，不能视为自动化完成。固定提交 `f5ab379cb6f009da322a295c19608ec144a55ec1` 的官方 bdpan-storage 文档列出 baidu-drive 1.7.7 / bdpan 3.8.9、`bdpan share` 及 0/1/7/30 天期限（默认 7 天），但文件操作仅限 `/apps/bdpan/`，不能假设能分享已有 Xtransfer 应用区对象，也不能用旧 fs_id 越过范围。

认证文档描述独立 OAuth 授权码、本地 Token 保存和自动刷新，不在此前临时 access_token 测试范围。外部 Skill 要求附带用户原话/会话标识做追踪；本项目只将其作为待评估文本，不执行、不发送。后续须确认不发送追踪文本及其他遥测的数据最小化方案。MCP 个人体验另用体验应用授权、仅供测试且不得正式使用，不保证现有应用或跨应用对象可用。

bdpan 保留为自动化候选，尚未安装、授权或实测；正式 API 的企业认证、购买和开通要求不变，商用准入、现有应用兼容性、调用/下载价格和额度仍需官方确认。若未来验证 bdpan，须另行具体界定安装、持久授权、应用区单份样例放置和建链范围；此前站点安全拒绝仍有效，不通过候选工具绕过。此次仅文档更新，无凭据/对象操作、付费或商务联系。固定来源及未知项见[分享服务调研](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/baidu-share-service.md)。


### BaiduPCS-Go 登录：优先只读诊断

按用户方向，优先研究 BaiduPCS-Go 登录后复用分享命令的可行性。历史实际错误是贴吧 HTTP profile 请求等待响应头超时，不是网盘分享业务拒绝；旧执行版本、认证入口和超时网络根因未留足可核验证据，不能断言 Cookie 无效或海外封禁。

当前正式 release v4.0.2 固定提交 `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d` 的登录支持 BDUSS/Cookies 和用户名密码分支，未找到此版扫码入口；源码存在不证明服务当前接受。用户初始化依赖贴吧资料查询，超时可向上传播阻断登录；这与旧错误相符，但不能倒推旧凭据有效。`force_login_username` 跳过校验并使用固定示例身份，不算可信认证，不执行。

同一版本默认跳过 TLS 证书校验，依赖中含带 BDUSS 的 HTTP 登录检查，账号会话会写入本地 JSON；与现有 Xtransfer OAuth 临时令牌范围不同。下一步可设计身份/资料解耦、证书/凭据 HTTP 防护、格式校验及假 transport 诊断，尚未实现。当前仅只读公开源码/非敏感记录，不运行客户端、读凭据或重试登录；此前站点安全拒绝仍有效，不能用工具切换绕过。真实登录、持久访问及指定对象分享须先有允许渠道并按工具/主机/凭据范围明确授权。详细固定来源、历史证据缺口和风险见[登录优先诊断](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/baidu-share-service.md)。


## 2026-11-09：M4 优先安全设计离线验证

PCS-Go 登录安全方案已形成独立离线模型：固定假凭据、仅内存 FakeTransport，检查严格 TLS/HTTPS、可信身份与可选资料解耦；身份无效/未知/错配时拒绝，只有模拟身份已建立后才容许资料超时降级；禁用 force-login 成功语义，输出固定安全状态码。12 项针对性及工作区全套 148 项测试通过，旧未提交实验保留。模型路径为虚构标签，不是百度接口；未修改或接入真实 PCS-Go、网络/认证设置，真实认证与分享资格始终为 false。

自动分享仍是目标，M4 尚未真实验收。后续需审查实际客户端补丁、可信身份接口、依赖/TLS/秘密全链路，并先具备允许渠道和对具体主机/构建/凭据范围的授权；不绕过既有站点拒绝。此轮无真实凭据或账户请求、无上传/建链/部署。详见[离线模型、测试与真实接线限制](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-auth-simulation.md)。


### M4：固定上游安全补丁候选

已保存针对 BaiduPCS-Go v4.0.2 提交 `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d` 的实际源码补丁：请求层严格 TLS、HTTP/重定向保护及身份未接线时登录/force-login/账号保存默认拒绝。逐文件基线、补丁适用性、实际离线应用和静态约束检查通过；主机无 Go 工具链，Go 编译及三项假 transport 测试未运行，不能称真实客户端已修复。身份接口仍未核实，资料降级没有真实成功路径；现有 Python 回归通过仅证明本项目未回归。无凭据、完整客户端执行或账户请求，既有站点安全拒绝不变，M4 尚未验收。见[补丁、调用链、验证与剩余风险](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/patches/baidupcs-go-v4.0.2/README.md)。


### M4 最后一轮审查与条件决策

固定源码存在 HTTPS Cookie 账号查询 `UK → PrepareUK`，调用链无需贴吧资料；但未核实当前受支持契约或本账号可用性。官方 OAuth uinfo 是另一授权通道，不能用于证明 BDUSS。补丁已补齐请求构造/响应读取错误脱敏，并明确回调、公开可变客户端及独立依赖不在完整保护保证内。补丁应用/基线/静态检查通过；Go 工具链缺失，现六项 Go 源码测试与编译均未执行。

确定结论：保留 PCS-Go 为候选，不选为 MVP 已可用自动分享后端。M4.1 诊断/模型完成；M4.2 缺源码级编译测试；M4.3 受控登录/对象访问、M4.4 自动分享均未执行。有限下一步是本项目主机经审查工具链上的离线补丁测试，随后才评估允许渠道与具体凭据/对象范围授权。无新安装、秘密、账户请求或对象操作；不绕过已有站点拒绝，不用旧 Python 回归充当 Go 补丁验证。详见[证据与条件决策](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/baidu-share-service.md)。


### 获准 Go 文件级验证已通过

在用户明确批准后，项目隔离目录内的官方 Go 1.27.3 linux/amd64 完成归档大小/摘要核验。两个已审查标准库依赖文件通过 gofmt、编译和六项离线测试；使用独立配置/缓存与子进程 seccomp 禁网，没有运行完整客户端、账户请求或真实凭据/对象操作。磁盘检查点均高于 5 GiB，未改系统配置。此结果替代此前“工具链缺失、六项未运行”的阶段状态，最终补丁已同步格式化结果。

M4.2 文件级验证通过，完整补丁包和依赖仍未编译验证；M4.3/M4.4 未执行。PCS-Go 仍是候选，尚不足选作已可用 MVP 自动分享后端，既有站点拒绝和真实操作授权边界不变。见[安装、隔离与测试证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/pcs-go-offline-2026-11-09.json)及[补丁说明](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/patches/baidupcs-go-v4.0.2/README.md)。


### M4.2 包级构建阻碍已定位

同一获准工具链/禁网环境中，全部 10 个补丁文件完成语法解析和格式检查，已测 helper 摘要未变、六项测试未重复。完整根包纯编译退出 1：隔离模块缓存缺依赖，GOPROXY=off 阻止模块查找；未生成/执行客户端，也未下载新依赖。固定 go.mod 声明 34 个模块，首次报错列 15 项；需先明确取得固定公开依赖/元数据及闭包核验的范围，才可继续离线包级编译。不能用 stub、用户缓存、其他设备或 helper 通过替代；M4.3/M4.4 未执行，后端候选结论不变。见[固定依赖清单与失败证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/pcs-package-build-2026-11-09.json)。


### M4.2 完整补丁客户端纯编译已通过

用户明确批准固定公开依赖获取后，隔离缓存内 34 个锁定模块归档及 185 份传递 go.mod 元数据均核验原 go.sum；无版本/锁文件变更、认证信息或用户缓存。恢复进程 seccomp 禁网后完整补丁客户端编译/链接退出 0，二进制未执行，无包初始化、账户请求或对象操作；大于 5 GiB 磁盘底线。旧缺依赖失败仍保留为历史记录。

现可确定“补丁能完整构建”，M4.2 构建阻碍解除；身份门仍默认拒绝，M4.3/M4.4 未验证，不等于自动分享后端已可用。后续真实验证须先具备允许渠道和具体身份/凭据/请求范围，既有站点拒绝不变。见[依赖范围、摘要和完整构建证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/pcs-full-build-2026-11-09.json)。


### 实际 requester 包七项回归通过

新增七项回归在实际补丁 requester 包（含审查后的 6 包非标准库初始化）中运行通过，覆盖真实构造/Req/Fetch/HTTPGet，而非仅两个 helper 文件。目标执行前启用 Landlock 文件白名单与 seccomp 禁网；自建目录外假文件/符号链接读取和网络 socket 均被拒绝，目标只得到空 HOME/配置和显式假值。

实际配置包的身份门/账号保存两项测试仅编译通过、未运行：74 个非标准库包初始化审查未完成，且包全局变量会定位配置目录。没有运行 main、账户请求、真实凭据或分享，无新增依赖或系统配置变更。M4.2 运行证据增强，M4.3/M4.4 仍待验证，默认身份拒绝与后端候选结论不变。见[测试范围及初始化/隔离证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/pcs-package-regression-2026-11-09.json)。


### 实际配置包两项受限回归通过

对 74 包初始化按选中文件和实际调用继续审查，明确绝对隔离配置路径早退、NewConfig 不加载文件、PCSConfig.init 并非自动函数，以及 protobuf 只读取当前受允许测试二进制等具体行为。专用配置测试目标在 Landlock 文件白名单、seccomp 禁网及空环境下执行，两项均通过：身份入口拒绝、假账号保存拒绝且未创建配置。越界假文件/符号链接与 socket 探针均被拒绝，独立 HOME 仍为空，无客户端 main、真实凭据/账户请求或新依赖。

先前配置测试“仅编译”缺口已解除；M4.2 有完整构建及 requester 七项/配置两项运行证据，仍不能推导真实身份或分享资格。M4.3/M4.4 未执行，默认拒绝和原站点安全边界不变。见[配置初始化审查与执行证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/pcs-config-runtime-2026-11-09.json)。


### M4.3/M4.4 接入契约候选与特征测试

已追踪 Cookie UK、贴吧 UID/现有 OAuth 的不同通道以及按 path_list 建链；新方案要求严格身份/预期账号与精确对象绑定，默认 unavailable 的可注入适配器和一次意图/unknown 核查，该句为严格验证层实现前的历史状态；目前验证层已实现，生产接线及真实访问仍关闭。实际固定源码的假响应特征测试两个顶层/十二子场景通过，确认 UK 可接受缺 errno/非正 uk、ShareSet 可接受缺成功码/ID 或非法链接等宽容缺口，不能当作安全或服务能力通过。编译需显式 -vet=off 避开已有无关路径诊断，未宣称默认 vet 通过。

现有 Xtransfer 对象访问、客户端 Cookie 契约/商用支持仍未验证；既有站点拒绝有效，先确认可验证的允许渠道，之后再分别审阅精确主机/构建、短期只读身份/对象、单次建链与清理范围。无真实秘密、账户请求或链接生成。见[源码依据、适配器契约和阶段方案](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-identity-share-plan.md)。


### 严格验证层实现与十五项测试完成

原 UK/ShareSet 缺口已形成独立 Go 候选响应验证层及 fixture-only 单意图账本，格式/编译/vet 和十五项受限运行测试通过，涵盖 JSON/身份/精确对象/期限绑定、规范 URL、未知不重试、映射冲突隔离与停止重放。原解析函数和真实入口未被打开或自动替换，无凭据/provider/账户请求/新依赖；候选 Principal/映射输入不算服务认证。

本组件的无凭据测试范围已完成。M4.3/M4.4 真实验证仍缺允许渠道依据和可信 Cookie 身份/指定 Xtransfer 对象/分享内容映射契约，不能用模拟或换工具推定放行。精确后续阶段范围见[接入方案](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-identity-share-plan.md)，实现/测试见[适配层说明](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/patches/baidupcs-go-v4.0.2/adapter/README.md)。


### 真实验证进入条件收敛（2026-11-09）

严格候选验证层已实现，十五项隔离测试是已有结果，本次未重复测试。生产可信接线与真实分享仍未完成。此前仅有可信转述的控制信息已由下节核实结果更新；拟议 Cookie 账户请求尚未尝试，不能写成百度 API 已拒绝。下一步先取得原访问控制提供方或管理者的非敏感范围说明及允许复核途径，不索取 Cookie、不换工具探测。详见[当前进入条件与候选阶段范围](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-real-test-readiness.md)。


### 拒绝元数据回填（2026-11-09）

协调方已核回：用户 Mac 的 Chrome 调用 `cua.createBrowserTab` 打开 `https://pan.baidu.com/` 返回 `isError=true`，拒绝来自 **Browser Use site safety gate**；未授予观察页面，未进入用户授权或 auto-review 流程，且明确禁止通过其他浏览器、间接执行、CDP 等实现同一被拒目的。规则 ID、具体维护方和正式复核路径仍未知。这不证明百度自身拒绝或所有 API 均被禁止，也不是替代通道许可。拟议 Cookie 身份/对象/分享请求仍未尝试。严格候选验证层已实现，生产可信接线未实现；此次仅回填事实，不重跑测试、不索取凭据、不重试或绕过。


### M5 本地进程与持久化窗口验收（2026-11-09）

新增 13 项真实子进程/合成故障窗口测试；独立预期提交副本中，工作流、space、upload_stage 必要回归共 65 项通过，排除历史未提交四项。SIGKILL 重开、两进程竞争及 fsync/replace 注入验证未重放已持久意图，残留 state.new 保留；新增只读 diagnose 返回固定原因，不修复/删除/重置或调用后端。5 GiB 保留线与真实后端关闭不变；未测试断电或真实远端 exactly-once，M5 整体及真实 MVP 仍未验收。 详见[工作流矩阵与复现](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-workflow.md)、[执行证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/m5-process-recovery-2026-11-09.json)。本轮不涉及百度账户或解除既有站点限制。


### M2/M3 协作停止边界（2026-11-09）

新增进程内协作取消/deadline 检查，HTTP 停止确认追踪在途请求/读取/关闭；20 项新增测试、23 个合成场景及干净副本必要回归 122 项通过（零失败/跳过，排除历史未提交四项）。低空间后拒绝新载荷；故意忽略取消的 fake 分片仍实际晚写 4 字节，说明阻塞调用无法被检查点抢占。永久阻塞无结果可用，不冒充停止成功；真实网络停止时限、后台写入上界及 M2/M3 整体验收仍未证实。 仅测试自有微小合成文件与禁网子进程，5 GiB 保留线、M4 登录/分享关闭不变。详见[停止契约和复现](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-stop-boundaries.md)及[机器证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/m2-m3-stop-boundaries-2026-11-09.json)。


### M4 官方 MCP 无凭据候选（2026-11-09）

官方 MCP 的无凭据候选已实现：只验证固定16字节合成任务与 README 字段，复用现有 Job 锁/持久意图，不新建账本、不解码未知 MCP 信封。新增17项及干净副本必要回归38项通过（零失败/跳过，排除历史未提交四项）；创建后注入超时，新进程重开同 Job 不再调用模拟创建。字段合格仍未验证，身份/应用范围及分享对象映射不被合成观察证明，live 始终关闭。 用户要求尝试原已回读样例建链，本次实际分享仍未尝试；未迁移/重传/读凭据/连服务器。真实阶段须先取得原控制允许依据及服务/应用/对象映射契约，不能借 MCP 绕行。详见[实现、测试与单次审批范围](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-share-candidate.md)、[机器证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/mcp-share-candidate-2026-11-09.json)。


### MCP 接入静态核查（2026-11-09）

公开固定源码现已确认 MCP SSE 入口 https://mcp-pan.baidu.com/sse 及 access_token 查询参数认证；demo 会向千帆发送 messages/工具结果、记录参数并异常自动重试，不能原样用于建链。stdio 注册的是上传工具。当前 token 有效期/scope、应用与分享权益仍未无凭据确认；真实连接器未实现，原控制允许依据仍缺。此次仅静态审查，未改代码/重跑测试/读凭据/连 SSE/建链或领取。 已知 endpoint 不等于允许绕行；下一步先取得原控制允许依据，再确认兼容应用/响应映射并审阅单次内存凭据使用。详见[静态审查与真实阶段](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-share-candidate.md)、[机器证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/mcp-access-static-2026-11-09.json)。
