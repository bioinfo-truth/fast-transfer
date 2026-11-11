# 路线图与决策

> 当前验收目标是海外业务VPS。既有Xtransfer上传/完整回读历史通过；原授权单次原生uinfo验证成功，应用绑定及分享权限仍未验证。不要用开发机授权代替VPS验收，也不重做上传或新grant；当前决策见[路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap)。

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


### 官方 MCP 锁文件证据纠正（2026-11-10）

纠正官方依赖证据：固定提交确有 uv.lock（96,472字节，blob a792c3d7eb17925a76e82af04d94050ef290fe1b），锁定 mcp1.6.0/httpx0.28.1/python-dotenv1.1.0/aiohttp3.11.16等并声明PyPI制品哈希。pyproject 是范围约束，不能据此说官方无锁；本项目尚未采用/完整审查该锁，也未验证Python3.14运行兼容。仅读取公开锁并修正文档/JSON，没有依赖下载、执行或重跑测试；真实接入阻碍不变。 详见[环境复用与纠错依据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-share-candidate.md)。


### M4 确定性 SSE 协议接入（2026-11-10）

已新增确定性 SSE/JSON-RPC 字节协议层，接到原固定合成文件核对及 Job 单次意图；保留 MIT 署名/许可证，无 LLM、凭据发现、秘密日志或自动重试。17项新增协议测试及干净必要回归42项通过（零失败/跳过，排除历史未提交四项）。验证的是内存HTTP/SSE流，尚无真实TLS/SSE driver、SDK运行或服务连接，真实身份/对象/建链均未尝试；原访问控制与具体凭据/应用范围条件不变。 详见[协议流程与范围](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-sse-protocol.md)、[执行证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/mcp-sse-protocol-2026-11-10.json)。


### 候选 HTTP/SSE 驱动真实本地验证（2026-11-10）

候选 HTTP/SSE 驱动已实现，新增21项真实本地TCP/TLS测试在干净副本全部通过（零失败/跳过），未重跑上轮42项内存测试。实际验证了TLS信任/主机名、跨域/重定向拒绝、握手/读取/慢头超时与关闭、已受理合成分享后ACK超时保持未知且同Job不重发。生产构造器及外部/凭据入口仍拒绝，本地工厂硬绑定回环；没有百度连接、真实认证/对象/分享/领取或原样例重传。 明确隔离本地测试工厂与生产入口；内核TCP单端口+应用回环绑定，无文件系统/完整网络沙箱。详见[实现与实际测量](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-local-https.md)、[机器证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/validation/mcp-local-https-2026-11-10.json)。

## 2026-11-10 纠正与官方驱动开发进展

此前把 Mac 浏览器打开 `https://pan.baidu.com/` 的 Browser Use site safety gate 拒绝泛化为官方 MCP API 的前置封锁，依据不足，相关历史段落中的“先取得原控制允许依据/联系维护方”不再作为官方 API 开发或验证的通用前提。不能重试被拒网页或用另一浏览器/CDP完成同一被拒网页访问；官方 API 的具体请求若遇新的控制拒绝，停止该操作，不绕路。

新增 `OfficialHTTPSDriver` 和独立 `SSEClient.for_official_readonly`：固定官方 SSE 域名/443，只接受调用者显式传入的临时 access_token，不自动读文件、环境、浏览器或回调，不执行 OAuth/刷新。使用系统 CA、官方域名 SNI/主机校验与 TLS≥1.2；首次请求解析官方域名，拒绝非公共地址，单次会话固定一个地址，不自动切换重试。GET 仅向固定官方 SSE 路径提交 URL 编码令牌；后续消息仅允许同 origin 的受限 session endpoint，无跳转或代理、无 LLM。关闭时释放令牌引用，不宣称内存安全擦除。继承现有时限/watchdog/关闭及脱敏；目前错误码仍沿用部分 `mcp_local_*`，不据错误码判断网络范围。

此阶段允许协议握手/工具清单及 user_info/file_meta 调用；所有分享和其他工具在发包前拒绝。它是实际外部传输代码，不是已完成的真实分享适配器：尚未把真实身份、精确对象、服务响应与现有 Job 持久单次意图接线。现有 fixture 分享保护继续保持，不能直接把真实驱动塞入 fixture 工厂。

新增13项合成凭据检查在 seccomp 禁网 runner 通过；真实 socket/TLS 被 mock，不构成官方实网证据。因共享 GET 路径增加了 override，针对受影响的21项真实本地 TCP/TLS 测试回归通过，零失败/跳过；未重跑旧42项内存测试。官方 DNS/连接/认证/工具契约/身份/原对象/分享/领取均未尝试，没有读取真实凭据或重传样例。

DNS调用者等待有界，但系统解析线程不能强制取消，超时后可能短期继续运行；线程不持有驱动或令牌。系统 CA 加载与 DNS 环境是本机信任边界，不宣称隔离全部宿主配置。查询令牌会到官方服务，客户端不记录不代表官方服务端不记录。

下一步：从既有可信私有任务收据确定精确原对象/账号/应用和允许使用的凭据来源；明确一次临时读取/内存使用并向官方 SSE 提交的权限，不扫描秘密、不要求聊天贴令牌，不新建授权。确认该凭据兼容 MCP，取得实际只读响应再实现真实身份/对象 decoder 和持久单次分享接线；未知结果不重发。用户分享意图已明确，无需再泛问是否想分享。

## 2026-11-10 显式对象绑定与候选分享接线

新增 ExpectedObject / BoundSession，官方只读工厂必须显式传入预期账号、应用及一个精确文件，已移除固定测试文件 ID 限制。严格 MCP 单文本 JSON 候选解码、uk 与唯一文件 fsid/path/size/MD5 匹配已实现；不把本地 SHA256、目录名或 caller 输入当作服务证明。真实业务信封/inputSchema、凭据应用权限和分享对象映射仍待验证，官方会话与 HTTP 层双重禁止真实分享。

候选状态接线复用现有 Job 锁及 fsync 持久未知意图，只有 ScriptedHTTP 可创建一次模拟分享；保存失败无创建，超时后新进程重开无请求重放，链接/码/私有标识不落盘，不新增真实账本或开启交付资格。干净副本新增绑定17项、受影响官方驱动13项及 SSE17项，共47项通过，零失败/跳过；均为禁网/合成业务，未读真实凭据、未连官方服务、未分享原对象。

剩余输入是可信私有收据的精确原对象定位、已获准的临时凭据来源与兼容应用权限；官方公开 README 尚未提供完整业务信封、应用声明及分享对象核实映射，缺项不猜。无需把浏览器网页拒绝扩大到官方 API，也不重复询问用户是否希望分享。详见[接线、测试与逐项缺口](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-binding.md)。

## 2026-11-10 官方 MCP 无凭据可及性实测

16:52（UTC+8），当前项目执行主机一次无认证GET官方SSE地址：DNS/TCP成功，TLS1.2证书链和主机名校验通过，HTTP **200 / text/event-stream**，无跳转，总耗时约0.237秒。未使用代理、令牌或OAuth，未访问网盘网页，未发业务/分享请求；没有遇到新的控制拒绝。此结果是当前主机的实际网络/HTTP证据，不是海外VPS结果，也不证明各地均可达。

事件流仅检查响应头，未读取事件/发initialize；SSE协议、认证、账号/应用/精确对象与分享权限仍未验证。暂不因网络可达性增加代理；下一步再按明确的最小只读协议范围检查事件/握手，若要求认证，核实短期凭据来源和兼容性，不扫描秘密。详见[实测与可执行调整](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-reachability.md)。

## 2026-11-10 官方无凭据 SSE 与 MCP 握手通过

17:02–17:03（UTC+8），三个有界会话合计3GET、1initialize POST、1initialized通知POST；全部TLS证书链/主机验证通过并关闭确认，业务/分享调用为0。前两次GET分别因旧profile不符停止、做脱敏结构诊断；第三次确认官方实际消息路由 `/message`、查询键 `sessionId`，initialize POST202，真实SSE返回协议2024-11-05，initialized通知POST202。仅会话内存使用真实查询值，没有输出/持久化它们。

无凭据最小握手已证实，认证/应用/原对象/分享权限仍未验证；未读令牌/发OAuth，也未访问被拒网页。生产客户端仍是旧 `/messages` + `session_id`，下一步应独立接入已实测的同域受限profile；本轮只改探针及证据，未扩大生产路由或调用业务。当前项目主机结果不能代替海外VPS测试。详见[逐轮结果、数量与调整点](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-reachability.md)。

## 2026-11-10 正式路由接线与工具发现

正式客户端现已支持已实测的同域 `/message` + `sessionId`，合成/本地旧profile独立保留；只允许精确路径/受限单查询，TLS、DNS固定、无代理/跳转/重试及日志保护不变。新增不带凭据的OfficialDiscoverySession，底层无token时禁止tools/call，发现会话自身也禁止业务RPC。

17:43:57（UTC+8）正式客户端实网：1GET+initialize/initialized/tools-list三次POST，HTTP200/202/202/202，TLS验证通过、383字节、约0.957秒、关闭确认。**无凭据tools/list返回空列表**，不能判断唯一原因或声称认证/账号/原对象/分享已通过。未读token/私有收据/新建OAuth/调用业务，也未测试海外VPS。

干净必要检查56项禁网+21项本地TLS通过，独立于官方实测。继续账号/原文件核验需要明确原VPS既有短期token的指定读取来源、同进程使用/向官方SSE查询提交范围与应用兼容性；禁止扫描/刷新/换应用，保留原对象。详见[真实结果、代码与具体缺口](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-official-discovery.md)。

## 2026-11-10 Xtransfer 授权元数据核查

仅检查既有非秘密任务记录及原VPS单个已指定凭据位置的lstat：位置存在、普通文件、非符号链接、root所有、0600；没有打开内容或取得任何令牌值。应用名称Xtransfer来自用户和历史样例记录，当前文件的实际应用/AppID绑定未验证。已检查记录没有实际OAuth授予scope、签发/到期时间的独立证据；过去上传/完整回读成功不能证明当前有效或MCP兼容。

若必要字段只在与秘密混存的JSON里，普通读取会取得秘密，超出本次元数据许可；下一步需独立脱敏元数据记录，或明确批准原VPS一次受审文件读取、只输出白名单元数据且不使用/提交令牌。当前未实施该读取，没有OAuth/刷新/业务请求，私有位置和标识不公开。详见[已知、未知及具体下一步](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/xtransfer-auth-metadata.md)。

## 2026-11-10 服务器终端本人无回显输入入口

新增mcp_terminal_readonly入口，先加载指定私有ExpectedObject记录、隐藏确认READ-ONLY，再由用户本人在前台控制TTY无回显输入已获准短期token；非交互/关闭回显失败拒绝，无stdin/getpass降级，不读旧秘密、不写环境/.env/历史/日志。固定官方TLS目的地、URL查询风险明确，退出释放引用，不承诺内存擦除或终端录制防护。

单会话先发现schema，匹配后至多一次账号及一个精确文件只读核对；未知schema/身份/响应停止。输入token不证明应用权限，真实分享门保持关闭，不写Job或新增账本；原持久单次意图和未知不重发接口保留。此次没有OAuth、真实token、实网服务访问或VPS部署。干净23项新终端检查+17项相关绑定/持久意图回归共40项通过，含真实自有PTY回显/恢复、EOF/取消/超时/SIGTERM、子进程argv/env/文件泄漏检查；都是合成token/禁网验证。详见[用户步骤、前提与限制](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-terminal.md)。

终端入口另有独立 `--discover-only` 模式，隐藏确认DISCOVER-ONLY后本人输入，只发现工具、无账号/文件调用，不需用户猜fsid。代码仅当前项目工作区就绪，解释器Python3.14.4已核实，VPS未部署。精确只读的私有原收据位置仍待明确；恢复收据只保留账号指纹时不能反推原始uk或伪造mapping。扩展测试初轮1项类型门/测试替身不匹配已修正，最终40项通过，初轮日志保留。

## 2026-11-10 使用现有Xtransfer的设备码路线

按用户更正，仅使用现有自有Xtransfer，不再以个人体验应用/共享AppID代替；应用数量不证明当前API权限或主体审核。官方固定SDK确认设备码GET与同应用AppKey/SecretKey的device_token换取，scope basic,netdisk；Xtransfer实际grant及MCP兼容未测。

新增固定官方TLS的设备码transport、300秒/30轮上界状态机和本人TTY入口：无回显同应用信息、用户自己核对官方页并批准、pending/slow-down受控等待、未知申请/兑换不重发。只私密显示user_code不显示device_code/token；后续另一个明确动作才交MCP工具发现，不直接读原文件或分享。API密钥走HTTPS查询、服务器可能发refresh/session凭据和持续grant的风险明确；客户端不存储/刷新，也不能承诺服务器不签发或退出撤销授权。

仅当前项目工作区就绪，VPS未部署；本轮未读真实密钥/令牌、未发device请求/授权/业务。干净24项新检查+23项终端检查共47通过，全部合成/禁网设备API，不冒称已认证。下一步需用户本人在选定主机输入原Xtransfer资料、确认scope/新grant并自己批准，不在聊天发秘密。详见[官方依据、安全边界与操作步骤](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/xtransfer-device-oauth.md)。

## 2026-11-10 用户设备兑换报告与MCP校验失败跟进

用户提供脱敏报告：设备兑换device_authorized_in_memory、basic netdisk、1次轮询，令牌未存储；MCP已到tools/list一次请求，本地mcp_sse_protocol_rejected后关闭确认。账号/原对象/分享仍未验证。此为用户报告而非本轮代理实网重放；通用本地校验码不能解释为官方权限拒绝，也不能据初始化通过宣称MCP认证成功。

新增固定枚举/计数/布尔的协议诊断，区分事件/行上限、EOF、SSE字段、RPC ID/信封、分页/结果形状，不输出会话、真实ID/游标、schema/meta内容或秘密。静态修正标准ListToolsResult可选dict/null _meta的错误拒绝，但历史实际触发点未知，大小及其他安全门不变；设备授权与MCP发现完成标志分开。干净78项禁网+21项本地TLS通过，不冒称已修复官方互通。

本轮无真实凭据/终端读取或OAuth/MCP/业务请求，不恢复旧token、不重授权。旧报告无法追补诊断；以后最小复测需单独明确有效token来源及一次仅协议发现范围，没有现成token不得自动新grant。详见[已知、候选原因、修正与非敏感诊断字段](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mcp-protocol-diagnostics.md)。

## 2026-11-10 业务VPS优先与当前原授权状态

按用户纠正，海外业务VPS才是MCP验收目标；开发机可用PCS-Go的路线判断不能代替VPS实测，两次匿名脱敏授权报告也不能归属主机/出口。撤下开发机授权命令作为当前业务步骤，不要求第三次授权。

业务VPS只读：Linux x86-64/Python3.13.5，PATH有64位x86-64 BaiduPCS-Go但未启动/登录；候选30份源码在内存compile通过，标准库/148项CA可用，未写部署文件或发官方请求。默认隔离Python不能导入fast_transfer不代表全盘无代码，当前缺确认的新入口目录/版本。已有上传/完整双哈希回读复用，不重传或迁移。

21:44（UTC+8）指定原授权位置lstat仍存在、root/0600/普通文件，未开内容。修改时间不是签发/到期；当前应用绑定、scope/期限及官方实时有效性仍未知，分享权限从未验证。用户新设备token未存储及约30天报告不能更新/证明VPS旧token状态。下一最小受限步骤是明确原地白名单元数据读取范围；真实有效性还需另行获准的VPS内存只读校验，先不用新grant。

另完成initialize超时分段诊断、缓冲计数语义和deadline分类修正：107项禁网/24项本地TLS通过，并非VPS MCP验收。原预算按当前代码不沿用设备轮询时间；pending81不是未消费证明。只准备无凭据源码包/部署计划，没有部署、改出口规则或使用秘密。详见[业务VPS前置与授权状态](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/business-vps-preflight.md)。

## 2026-11-10 原VPS授权元数据已原地提取

22:07（UTC+8）在业务VPS对单个指定旧授权文件用已审阅提取器做内存解析，只传回白名单元数据：scope basic netdisk，expires_in=2592000秒（30天），created_at换算为11月7日01:49:56（UTC+8）。未取得非秘密应用名/AppID、明确签发/绝对到期字段；不把created_at或mtime当签发时间，故当前有效性仍未确定。完整配置/秘密未离开VPS，未写回或刷新，分享权限未验证。

10项合成禁网检查通过，实际提取源码哈希一致；不是在线认证验证。最小下一步候选是在VPS原地用旧access_token仅一次原生网盘uinfo，输出错误码/匹配布尔、不查quota/文件/分享。该接口是旧用途的身份核验环节，但本次元数据许可不自动包含提交凭据；明确单次服务/读取/结果范围前不发请求，不再次做设备授权或假定旧token适配MCP。详见[已取得字段及准确边界](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/xtransfer-auth-metadata-result.md)。


### 2026-11-10 原授权单次只读验证

业务VPS原地向原生网盘官方uinfo接口请求一次，HTTP 200、errno=0且身份结构符合预期，说明原令牌在当次请求时被接受。无可信旧账号指纹输入，账号匹配未核验；应用绑定、MCP兼容、分享权限仍未知。无代理/重定向/重试，TLS校验开启，连接已关闭；未刷新、扩权、上传或分享，凭据与身份内容未导出。[脱敏记录与边界](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/xtransfer-auth-metadata-result.md)。


### 2026-11-10 原样例分享推进：原对象匹配，MCP网络阻断

已适配旧账号哈希和原任务mapping；业务VPS当前账号及唯一原文件ID/路径/大小/类型、转换后MD5匹配，历史完整SHA256收据复用，未重传/重新完整回读。54项相关禁网测试通过。官方MCP首次连接在TCP阶段3秒超时，随后无凭据10秒复核及两个IPv4/一个IPv6逐地址探测均未建立TCP；TLS/HTTP及令牌提交均未发生，分享请求0、链接0、连接均关闭。**本次当前VPS直连MCP无法建链，尚非官方权限拒绝或永久不支持结论。** 恢复同官方域名443链路后继续真实schema/原对象匹配及单次分享接线，不重授权。[证据与断点](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/original-sample-share-progress.md)。


### 官方替代路径只读复核（2026-11-10）

VPS对两个MCP IPv4目标有单播出站路由，IPv6路由查询失败；nft表清单为空，legacy IPv4表清单为空，未见已查范围内显式本机拒绝，供应商/上游仍未知。未重复连接测试或改设置。原生REST分享是独立官方候选，但既有资料要求服务开通，用户历史未开通；现有Xtransfer资格/应用绑定/最新收费未确认。当前官方Go SDK未提供Share服务。不能把MCP网络失败归纳为全部官方路径不可行，也不能仅凭有REST接口就试建链；最小下一步是既有供应商出站策略或Xtransfer服务列表的只读事实核实，若须企业认证/付费开通则由用户决定。[依据、边界与缺口](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/sharing-alternatives-readonly.md)。本轮凭据读取/分享请求/网络设置变更均0。


### 2026-11-11 候选：海外上传、境内仅建链

用户提出将建链放在境内，文件无需回传或重传；这是可拆分架构，尚未运行成功/选为默认。境内仅检查当前PATH、三个常见安装位置及当前用户默认配置metadata：未发现BaiduPCS-Go安装或默认配置，专用配置目录环境变量未设置；没有扩大搜索、读取秘密或启动CLI。现有项目安全补丁仍为未部署的候选，不能当作实际客户端版本或认证成功。账号/原对象境内核验及分享请求均0；具体缺口为已知安装来源/安全版本和既有本机认证，VPS令牌不迁移。[架构及前置证据](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/domestic-sharing-candidate.md)。


同轮安装进展：用户明确授权安装并确认两端同账号；境内已安装固定v4.0.2源码的项目安全候选构建，版本输出v4.0.2-dev，产物哈希与历史构建收据一致。PATH入口目前仅允许隔离空配置、内核禁网的版本/帮助；四项实际启动/命令拒绝检查通过。**不是可正常登录分享的正式版**，真实认证/分享接线仍缺，用户账号确认不代替境内会话核验。未读取/复制凭据、登录、新授权或分享，不重传原样例。[安装事实与限制](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/domestic-sharing-candidate.md)。


### 2026-11-11 一次性内存登录入口已准备

新增项目子流程`BaiduPCS-Go login --session-only`，不进入原HTTP贴吧初始化或PCSConfig保存。严格固定wappass/pan HTTPS、证书/主机校验，无代理/跳转/自动重试；密码最多提交一次，验证码要求即停，Cookie仅内存，pan身份只接收BDUSS。账号密码隐藏输入经同机私有管道，不进入argv/env/配置。13项Go禁网、4项本地TLS、6项生成PTY及6项无凭据安装检查通过，百度认证/分享请求仍0。旧WAP协议真实兼容性未知，验证码续办和同会话分享未实现；退出不保留本机会话，不等于注销服务器会话。后续仅需本人具体批准一次新登录+固定身份查询，不默认保存秘密。[代码、风险和可执行步骤](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-login-session-preparation.md)。


### 2026-11-11：同一会话原样例分享入口

已安装项目自定义 `BaiduPCS-Go share --session-only` 合并入口；本轮只做合成、本地TLS及无凭据检查，未真实登录或分享。一次认证后依次匹配原账号、精确原文件、持久单次意图、创建一次并核对自己分享记录，私密链接只进入本人终端；未知结果跨进程阻止重试。21个Go顶层测试、5个本地TLS测试和14个前端测试通过，编译/vet通过。

实际使用仍需准备来自原任务记录的可信私有清单、确定有效期及终端提取码，并明确允许读取一页自己的分享历史（可能包含其他记录元数据）。不要要求本人先临时登录再退出重做。旧密码协议及真实返回格式在线兼容性未验证，记录匹配不证明接收端可访问；路径创建的并发变化风险只能事后检测。详见仓库 `docs/pcs-combined-share.md`。这不是已完成真实分享或MVP交付的声明。


2026-11-11补充：用户明确批准两机最小元数据传输后，原指定五份记录已在VPS原地关联校验，九项ExpectedObject字段已传至境内私有目录，字段/摘要/本人所有权及0700目录、0600普通文件检查通过，安装产物哈希匹配且无已消耗意图。SSH当前恢复，前次exit255历史原因未知。真实认证与分享未执行，未重复上传；交付本人按1天期限在同一流程终端输入提取码及账号密码。私有路径和值不公开。


### 2026-11-11：按用户选择恢复原生模式

用户倾向原生BDUSS/Cookie流程并明确要求切回。默认命令已切换到固定上游v4.0.2的局部安全修正版，恢复原生登录、配置保存和分享。只保留TLS校验、贴吧HTTPS、默认重定向拒绝及隐藏Cookie输入等具体安全修正；自定义密码/单次分享实验不再是默认入口，旧`--session-only`操作步骤撤回。本人用`BaiduPCS-Go login --cookies-prompt`在终端隐藏输入，随后仍走原生函数并以明文保存本机配置（新文件0600）。

编译、相关包vet、两个本地安全测试及三项禁网空配置检查通过。未读取凭据、真实登录或分享；在线兼容性未验证。旧私有原样例清单保留、没有重复上传，原生分享没有实验companion的持久单次意图保护。详情见仓库`docs/pcs-native-mode.md`。


用户进一步选择分别提供BDUSS和STOKEN。已安装`BaiduPCS-Go login --bduss-prompt`，在本人终端依次隐藏输入两项，再交给原生登录及本机配置保存；不要求完整Cookie或账号密码。合成PTY与禁网帮助检查通过，未真实登录或分享。


### 2026-11-11：本人报告原生分享成功

用户报告BDUSS/STOKEN原生登录成功，并提供原样例meta输出；文件ID、精确路径、大小、MD5与已批准的私有原始期望清单四项比较均匹配。用户随后执行1天期限、随机提取码的原生分享命令，回报含分享ID、链接、提取码的成功输出。代理未读取登录配置、创建分享或独立访问链接。公开记录只保留结果，不含分享ID、链接、提取码及私有对象/账号标识；期限为请求值，尚未独立核实服务端到期。

海外上传与境内原生建链路线已获得这一次小样例的本人操作成功回报，无需重新上传。接收端提取/下载、实际吞吐量、大文件稳定性和自动化交付仍待验证；不将用户回报等同代理独立端到端验收。


2026-11-11接收端验收补充：用户明确确认已通过未登录浏览器验证提取码有效、文件可正常下载。本次原公开小样例的“海外上传 → 境内原生分享 → 接收端领取”交付闭环记为用户确认通过；不是代理独立测试，也不声称本次领取后做了新哈希核验。分享绝对到期时间、大文件吞吐量、持续稳定性及订单自动化仍未验收。


### 2026-11-11：VPS测试磁盘清理

按用户要求，删除历史1 GB/5 GB合成源/回读五个路径及三处可重建编译缓存，清理软件包下载缓存；保留结果、事件、配置、程序/源码、原NCBI样例及五份原始记录。可用空间由7.79 GiB增至22.65 GiB，释放14.87 GiB。原样例/记录/授权文件存在性复查通过，未读取凭据或操作云端。此前大样例本地源/回读副本“保留”的描述只适用于当时，现已清理；历史验收结果不变。

上传后端候选建议：VPS优先评估BaiduPCS-Go原生客户端、OpenList+rclone保留备选，尚未确定替换。境内原生分享成功不证明VPS原生上传性能，OpenList已有历史5 GB上传及完整回读记录。建议先同文件/同出口比较速度、磁盘峰值和断点恢复。详见仓库`docs/vps-disk-cleanup-2026-11-11.md`。


### 2026-11-11：官方API主上传路线与SDK复用

用户同意VPS沿已验证的官方OAuth/API上传路线推进，并要求适度复用官方Go SDK以减少维护；境内继续原生建链，OpenList+rclone保留备选。此前VPS优先原生客户端的表述修正为候选，不能将境内登录成功外推到海外。

已新增直接依赖固定SDK版本的独立兼容性模块，五项禁网合成HTTP测试和vet通过：验证三步上传、已有uploadid接线及低层合并未知不重试，确认实际multipart会缓冲整个分片且返回MD5需调用方核对。优先复用api层参数/响应和请求封装，项目保留预算、持久恢复、摘要检查及未知结果策略，不直接采用scene默认重试。尚未接入生产适配器或部署VPS；Python编排与Go SDK之间仍需设计窄接口并核算维护成本，不为SDK重写整个项目。具体由既有Issues #4/#5/#2跟进，详见仓库`docs/official-sdk-reuse.md`。


## 2026-11-11当前状态及建议MVP顺序

小样例已完成官方API上传/双哈希回读，并由用户确认境内原生建链、未登录领取下载；后文早期“尚未分享/领取”是历史阶段，不能作为当前状态。通用任务真实接线、完整恢复和容量边界仍未完成，SDK目前仅完成固定版本5项禁网兼容性验证。

建议下一步依次为：统一通用任务入口及上传薄适配（#4/#5）→ 官方API路线真实大文件/空间/故障联合验收（#2/#4/#5）→ 逐文件确认后清理与私有交付单、人工建链（#4/#7）→ 人工录单少量不同任务试运营（#7）。保留5GiB磁盘底线；先按实际容量限制文件，超容量转人工。SDK复用以减少重复维护为目的，不为此重写所有编排。

项目号解析（#6）与淘宝接单自动化（#8）放在交付稳定后，不作为既定人工MVP前置。以上是建议执行/验收顺序，不代表真实测试已经执行或新增上传与凭据动作已获批准。详细清单见仓库`docs/mvp-next-steps.md`。


### 2026-11-11：Goal持续推进与通用任务入口

已按用户要求启动持续Goal，范围为人工录单MVP，不提前包含淘宝/支付/解析插件。新增通用`fast_transfer.task`：审核manifest快照、多文件串行状态、私有SQLite事务/任务锁、源下载与完整源中断后重验、部分源显式重启。远端操作意图先记unknown，跨进程消耗键不可重发；仅提供严格收据持久接口，SDK上传后端尚未接入，状态明确不称云端或交付成功。

18项新增禁网测试加96项相关回归共114项通过，含实际子进程SIGKILL后源恢复和未知提交防重。复用已有下载/空间检查及标准库SQLite；未读取凭据、发新远端写入或部署VPS。源阶段仍为source-only空间准入，不代表真实上传全过程预算，HTTP Range字节级续传未实现。具体下一步为SDK上传薄适配及同任务恢复/核验/清理/交付接线，见仓库`docs/mvp-task-entry.md`及既有Issue #4/#5。


### 2026-11-11：半自动MVP的SDK请求编码接入

保持同一Goal的半自动方向：人工审核manifest → VPS源下载/校验/官方API上传回读 → 国内原生客户端核对新对象并人工建链 → 本人领取确认并记录交付。不另起任务，不重传原样例，不跨机搬凭据。

实际SDK代码已用于目录/预上传/分片/合并的请求生成，Go编码进程禁网、不接收令牌；Python保留现有HTTP与严格响应校验。新增单片memfd、输出/时间限制、内存准入估算及目标/字节比较。11项Go测试和vet、122项Python集成/回归通过，包含32MiB单片往返；不是VPS吞吐量或RSS验收。通用Task的上传执行/会话持久恢复、核验后清理和私有交付记录仍待接线，未部署或做新账号操作。

下一轮真实验收候选已准备为不同的公开蛋白FASTA（902,395字节，官方大小/MD5元数据已匿名核对），见仓库`examples/ncbi-ecoli-protein/`；文件内容尚未下载。候选范围为新独立Xtransfer目录中的一个小文件及必要上传/回读、境内1天随机码分享/领取，仍须在执行前明确新账号与交接范围，不沿用原样例单次许可。请求适配及可用/待接命令见`docs/sdk-request-encoder.md`和`docs/mvp-task-entry.md`。


### 2026-11-11：通用上传执行器与持久恢复

通用Task已接实际官方SDK请求编码、受控API上传与完整流式回读。目录/会话/分片/合并先保存意图再发请求，已确认操作跳过；未知操作在认证读取前停止，尚缺通用只读核查/人工裁决入口。任务设置摘要及账号/源/目标绑定用于限定执行范围，合成任务永不升级为真实核验。

34项针对性测试及相关回归共211项禁网测试通过，使用实际SDK编码器与合成响应；未部署VPS、未读取真实凭据或创建新云端对象。新增上传执行器强杀验收、核验后清理、私有交接/交付记录及不同真实任务验收仍待完成，Goal保持进行中。命令、输入输出和恢复限制见仓库`docs/mvp-task-upload.md`；工作继续由Issue #4/#5/#7跟踪。


### 2026-11-11：私有最小交接导出

新增通用`fast_transfer.task_handoff`命令，只允许全部文件真实API完整核验、无未知操作且源/对象摘要匹配的任务导出。严格字段白名单不包含认证或上传会话，导出至新0600私有文件并返回文件SHA256；不创建分享或宣称交付。6项新增及34项相关禁网测试共40项通过，合成记录不是新实网验收。国内导入校验、出处整合的私有交付回填、清理及未知操作核查仍待实现，详见仓库`docs/half-automatic-handoff.md`，Issue #7继续跟踪。


### 2026-11-11：逐文件核验后清理

通用`fast_transfer.task_cleanup`已实现：实际云端完整核验且无未知写入后，只删除指定本地载荷，保留记录/其他文件/云端对象。清理前重验双摘要及文件身份，持久删除意图；删除前后中断可重开任务恢复，异常身份或未核验/合成任务拒绝。单个文件核验即可清理，不要求同任务全部完成，因此串行任务可复用磁盘；清理后仍可导出私有交接。8项新增及40项相关禁网测试共48项通过，含实际子进程删除后SIGKILL恢复。没有删除实际VPS载荷，不等于上传强杀/真实磁盘验收；国内导入核对、交付回填与未知操作核查仍待完成。命令和限制见仓库`docs/half-automatic-handoff.md`，Issue #4/#7跟踪。


### 2026-11-11：国内离线核对与人工领取私有收据

新增`fast_transfer.delivery`：按发送方经可信渠道核对的导出摘要和预期账号校验私有清单；记录本人原生meta核对、分享和领取观察，输出新0600私有收据。严格匹配精确对象，pending/failed不标交付；confirmed需未登录下载与有效期内确认，并明确证据是操作人员声明，非程序独立验证。终端不输出链接或提取码，不自动建链、重传或回传凭据。7项新增及48项相关禁网测试共55项通过，均为合成观察；未做新真实账号操作。出处整合/源Task关联、未知操作核查及真实任务验收仍待完成。命令与观察字段见仓库`docs/private-delivery.md`，Issue #7跟踪。


### 2026-11-11：来源出处整合及源Task关联

v2私有交接纳入审核manifest及摘要，保留来源/版本/校验出处/分发依据并与对象名称、大小、摘要匹配；v1缺出处清单需重新导出，不手工升级。新增`fast_transfer.task_delivery`离线校验私有人工收据并关联源Task，重复幂等、历史追加、confirmed不被pending/failed回退。Task状态仅输出领取标志及人工证据类型，不打印分享信息；收据跨机传送仍须明确私有范围，不自动传送或搬凭据。7项新增及55项相关禁网测试共62项通过，均为合成记录，未做新实网或跨机交付。剩余重点为未知操作核查、上传强杀/资源联合验证及不同真实任务验收；Goal保持进行中。操作见仓库`docs/private-delivery.md`，Issue #7跟踪。


### 2026-11-11：未知commit的只读精确对象核查

新增任务核查入口，仅接管唯一未知操作为commit的情况。操作人员提供私有精确对象定位，程序只读核对账号/原目录/对象并完整回读双摘要，与重新读源匹配且停止确认后才保存commit及核验收据；不重复写入。错误或缺失对象仍保留未知，其他未知阶段不自动接管。7项新增及相关回归共106项禁网测试通过，使用实际SDK与合成服务器，未做新真实账号操作。目录/预上传/分片未知、快速完成分支仍待处理；上传强杀/真实资源及不同任务领取验收未完成。命令和边界见仓库`docs/unknown-commit-inspection.md`，Issue #5跟踪。


### 2026-11-11：上传exec/SIGKILL/再次exec验证

新增独立进程worker与持久合成服务状态，覆盖会话确认、第一片确认、合并确认后的实际SIGKILL与新exec恢复，以及远端合并响应丢失窗口。前3场景已确认写请求计数保持1；最后场景普通恢复停止，随后新只读核查进程完整回读后接续，不重发合并。2项新增测试含4场景，与相关回归共108项禁网测试通过，实际SDK编码器、合成云端/载荷，结果不标真实核验。未做新账号操作或VPS部署，不代替真实资源/服务器持久语义/断电验收。下一步准备版本化部署和不同公开小任务的具体实网范围，再逐步开展大文件与资源故障验收。详情见仓库`docs/mvp-task-upload.md`，Issue #5跟踪。


### 2026-11-11：独立VPS运行版本与无凭据检查

运行版本2d83444已安装新的私有目录，不覆盖原样例/旧程序或授权配置，不切换常驻服务。打包载荷和SDK许可证共49文件；48个载荷摘要/权限/所有权及语法检查、7个CLI帮助入口通过。VPS实际禁网helper完成目录及4MiB单片编码，未发送API请求；一次编码父进程峰值RSS48,512KiB、helper29,244KiB，不能当作完整任务资源SLO。

不同公开蛋白候选已建独立pending任务，上限1MiB，尚未源下载/读取凭据/新建百度对象。已向本人请求该单文件实测与最小元数据交接/核验后载荷清理范围，待答复前不执行账号动作，原生分享及领取由本人操作。后续仍需小任务闭环、大文件/真实资源和故障验收。部署依据与命令见仓库`docs/versioned-runtime.md`，Issue #4/#5/#7继续跟踪。


### 2026-11-11：通用运行资源采样

下载/上传/未知commit核查CLI新增有界周期采样：任务所在磁盘最小采样可用空间、父进程/最多64后代的RSS采样峰值、时间及采样完整性标志，异常路径停止线程；不采集命令行、环境或凭据。采样可能漏瞬时峰值并重复计共享页，不替代现有预算，也不改变真实核验/交付状态。4项新增及相关回归共112项禁网测试通过，含实际24MiB子进程。当前已安装2d83444尚不含此后续模块，实际任务前需选新版本。新文件范围仍待本人答复，没有执行账号操作。详细依据见仓库`docs/runtime-resources.md`，Issue #2/#4跟踪。


### 2026-11-11：含采样的VPS版本与完整验收缺口

63a9840已独立安装，49载荷摘要/权限/所有权及语法核验通过；实际目录/4MiB编码期间9次采样完整，父/进程树RSS采样峰值38,140/58,192KiB。只是离线编码，不等于上传资源验收。候选仍原pending任务、设置摘要相同、未知操作0，无源下载/认证读取/百度请求。原版本、原样例和旧目录保留。

已整理完整MVP要求与证据：代码/合成测试不代替新真实任务、本人分享领取、大文件/令牌失效与实网资源故障验收。当前新单文件范围连续等待本人答复，不能从Goal自动继续推断确认；独立部署准备已完成。具体下一执行顺序、人工失败处理/保留边界见仓库`docs/mvp-acceptance-status.md`。Goal未完成，既有Issue及草稿PR保持开放。


### 2026-11-11：恢复推进并完成通用任务新小文件实测

用户明确现有OAuth令牌已足够，并要求继续推进；既定MVP范围内沿用原地令牌，无需用户名密码，不按每个小文件反复确认。此前等待范围的记录是历史阶段，现已执行新任务。

902,395字节公开蛋白文件：源阶段0.63秒，官方SDK/API上传+完整MD5/SHA256回读18.39秒；四项写操作确认，未知0。v2清单已私有交接，境内原生meta核对path/fs_id/大小/MD5匹配，已有登录状态成功创建一次1天随机码分享。pending私有收据已关联源任务，核验后仅清理本次本地载荷，记录/云端/原样例保留。领取问询已发给本人，尚未确认，delivered=false。

上传/回读RSS采样父/进程树34,664/44,792KiB；耗时含控制及回读，不能当带宽，大文件和实网故障仍未验收。分享链接/提取码和私有标识不进公开Wiki。详见仓库`docs/protein-pilot-2026-11-11.md`及对应机器可读证据，Issue #2/#4/#5/#7继续跟踪，MVP未完成。


### 2026-11-11：本人领取确认，新小任务闭环完成

本人在未登录领取问询下明确反馈“已提取并下载成功”。已追加新的私有confirmed观察/交付收据并关联源Task，现delivered=true；pending→confirmed历史保留，本地仍cleaned、unknown=0，没有新上传或重复分享。领取证据为本人明确反馈，非程序独立浏览器/领取文件哈希复验。由此新902,395字节通用任务已完成源→API/双摘要回读→境内原生分享→本人领取→私有记录/清理闭环。

完整MVP仍需代表性大文件、不同manifest与真实资源/故障试跑，不将单个新小任务当作全部验收。公开证据与状态已更新，原样例/云端对象保留，Issue #2/#4/#5/#7及草稿PR继续跟进。


### 2026-11-11：原Goal恢复与代表性manifest准备

原Goal已由应用侧恢复为active，目标内容不变，不新建重复Goal。小样例阻碍已解除，后续按原授权继续既定MVP工作，不重复成功样例。

已匿名核对NCBI GRCm39目录、3项官方HEAD大小及MD5清单，准备两个新manifest：834,262,758字节FASTA＋7,187字节报告（多文件串行），随后1,133,653,005字节GenBank。8MiB分片为100＋1和136，单文件限额分别1/2GiB；第二组默认1GiB确实拒绝。预算规划约6.61/6.91GB磁盘、SDK内存含余量约403MB，本次VPS观测空间/内存有余量，实际账号分片资格仍须执行前核查。

已明确首片回执持久后停止/新进程同Task接续的实网测试方案；未知请求不重发，900秒执行上限不等于观察超时就重启。当前仅准备和intake/限额验证，未下载新载荷或创建网盘对象，不把准备当验收成功。详见仓库`examples/ncbi-mouse-grcm39/README.md`和budget.json，Issue #2/#4/#5跟踪。
