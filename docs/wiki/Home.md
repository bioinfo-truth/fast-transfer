# Fast Transfer 项目 Wiki

> 当前验收目标是海外业务VPS。既有Xtransfer上传/完整回读历史通过；原授权单次原生uinfo验证成功，应用绑定及分享权限仍未验证。不要用开发机授权代替VPS验收，也不重做上传或新grant；当前决策见[路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap)。

面向中国境内科研用户，提供海外公开生物信息数据的代下载和百度网盘交付服务。

## 当前 MVP 方向（2026-11-08）

从工具验证推进到最小服务：操作人员人工录入公开 HTTPS 文件链接/manifest → 下载及源站校验 → 百度上传及核验 → 分享交付 → 中国境内领取校验。先不做淘宝、支付、项目号自动解析、完整网站或收费；跨 OpenList 服务重启的分片恢复不是 MVP 前置。

M1 输入契约与真实 NCBI 小样例、M2 本项目主机的源下载校验已通过；M3 新一轮百度上传、M4 分享、M5 完整任务恢复、M6 国内领取尚未通过。实现处于评审分支，未部署或收费，详见 [MVP 范围与输入](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。上一轮临时令牌测试许可不作为新一轮持久配置许可。

M2 补充状态：后端感知的同盘/分盘预算组件、未知开销拒绝和离线动态检查已完成；实际上传/回读过程的空间保护仍待 M3 联调，不能视为整个 M2 已验收。详见 [MVP 范围与输入](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。

M3 当前状态：单次获准真实 NCBI 小文件已完成上传及完整回读双哈希核验；初次解析失败后在原空目录安全续办。一般模拟入口不变，实际分享/境内领取及完整服务验收尚未完成，详见 [MVP 当前交付](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。

M4 当前状态（2026-11-09）：固定 PCS-Go 安全补丁完整纯编译及七项实际请求层包回归已通过，配置包两项受限运行亦通过；身份入口默认拒绝，真实登录、对象访问与自动分享仍未验证。依赖获取和编译证据见本页末尾，旧缺依赖记录为历史状态。

下方工具记录及后续实验计划保留为此前快照，不能替代当前 M1–M6 状态。


- [产品与架构](https://github.com/bioinfo-truth/fast-transfer/wiki/Product-and-Architecture)
- [路线图与决策](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap)
- [测试方案](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)
- [高速传输工具调研](https://github.com/bioinfo-truth/fast-transfer/wiki/Transfer-Tools)

早期概念验证方向：美国 VPS 公开数据下载与直传；项目号解析和淘宝接入仍是后续候选。当前执行范围以上方 MVP 为准；所有性能、续传、分享及平台权限均以实测为准。

## 当前工具方向（2026-11-07）

网盘适配基线改用 OpenList + rclone；直接 OAuth/API 路径继续承担分片控制与持久恢复实验。BaiduPCS-Go 作为源码参考，借鉴动态节点、上传分片和恢复状态的设计，不依赖其 Cookie 登录，也不沿用其跳过 TLS 校验的设置。上传节点择优仍为待实现、待测方案：优先在当前 uploadid 的官方 `locateupload` 返回的 HTTPS 候选中比较实际分片吞吐及失败率，不能把旧域名清单或随机轮换当成已验证加速。

历史 AList 测试名称及数值保留，不改写成 OpenList 成绩；OpenList 不能继承 AList 的上传/续传验收。仅更换工具不会自动消除全文件缓存或保证更快。

## 验证总览（2026-11-07）

| 项目 | 状态与证据 |
| --- | --- |
| 1 GB AList + rclone 基线 | 已通过。精确大小 1,000,000,000 字节，上传、远端长度及完整回读 MD5/SHA-256 一致；见下方运行标识及校验值。 |
| 5 GB AList + rclone 基线 | 已通过。精确大小 5,000,000,000 字节，上传、远端长度及完整回读 MD5/SHA-256 一致；无人工中断或第二轮完整重传。 |
| 百度云端分片续传 | 直接 OAuth 路径已通过 256 MiB、8 片的短时跨进程恢复和最终双哈希校验；AList/OpenList 云端恢复仍未验证。完整重传与续传分别记录。 |
| 64 MiB 本地 WebDAV 中断实验 | 中断后重传及内容校验通过，仅为本地存储实验，不证明百度分片复用。 |
| OpenList 基线 | v4.2.9 已完成隔离准备，发布包 SHA-256 已核验；本机 WebDAV 冒烟结果见工具记录。未导入百度凭据或进行 OpenList 云端上传。 |
| 小磁盘 | 百度驱动实测需要全文件缓存；逐文件预算可用，超过本地容量的有界分片方案尚未实现。 |
| 交付 | 自动分享、境内客户领取及长期运行仍待验证。 |

1 GB 成功运行标识：`20261107T012600Z-899d7fa6`。上传约 195.38 秒、回读约 147.67 秒；缓存峰值 1,000,000,000 字节，最低磁盘空闲约 23.21 GiB。速度为单次实验，不能当作承诺。源文件与回读文件共同校验值：

```text
MD5     5ece53357439de59fabbb6ab99510bfd
SHA-256 b7ab02a22bd8aec8fddd19ebed18eb5d86601a398dd6fdc3ad977120cc07b8bc
```

首轮运行 `20261107T012108Z-f46523f0` 在短超时配置下以退出码 5 失败，发送约 350 MB；检查没有完整远端对象后，延长客户端超时、换新路径进行一次有限重传，才完成上述往返校验。首轮超时根因未严格对照确认；这不是续传成功。脱敏 `result.json`、阶段事件及测试数据保存在隔离实验目录，未公开原始配置、日志或私有账号资料。早期小文件及本地对照证据见[测试方案](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)和[工具实测记录](https://github.com/bioinfo-truth/fast-transfer/wiki/Transfer-Tools)。


5 GB 成功运行标识：`20261107T013816Z-c7e6ddb6`。超级会员身份经现有授权核实；默认 32 MiB 分片，对应 150 片（根据身份、源码及长度计算，未独立抓取逐片回执）。上传约 981.53 秒、回读约 671.33 秒，全流程约 1,792.59 秒；上传平均约 5.09 MB/s（含全量缓存等待），回读平均约 7.45 MB/s。rclone 使用 16 MiB/s 限速，不能视作网络极限；该参数不直接限制 AList 自己到百度的上行。缓存峰值 5,000,000,000 字节，最低空闲约 13.90 GiB。源与回读文件校验值：

```text
MD5     3976b897f4dd8a703575ca423d681d26
SHA-256 bf4b2872e3e2bc6825841472bb8ba0fff24a867eebb3b3683da10ae7a5f58996
```

该轮网卡总接收 5,074,590,582 字节、总发送 5,054,668,161 字节，包含协议和管理开销，不等同于服务商账单；不限流量来自用户说明。rclone 没有记录错误退出，未触发停止/完整任务重跑；AList 内部分片重试及 TCP 重传未单独计量，不能写成零重传。临时服务已停止，测试源、回读副本、私有原始记录和云端对象保留；没有分享、覆盖、清理已有资料或执行中断实验。原始记录保存在相应隔离运行目录，公开总览仅给出脱敏运行标识、指标和校验值。1 GB 和 5 GB 均为确定性非敏感生成数据，不能替代真实数据库源站性能测试。

## 直接 OAuth 补充实验（2026-11-07）

运行 `20261107T022422Z-74737a86` 使用官方 API 与现有应用授权，默认 TLS 校验、动态 HTTPS 上传域名、32 MiB 分片、单线程。新 1,000,000,000 字节文件的 30 片上传、远端大小及完整流式回读双哈希均通过；上传阶段约 116.02 秒（含 8.75 秒源重验），回读约 654.51 秒。不同时间、内容、端点及客户端限速条件，不足以据此断言比 AList 稳定更快。已有本地文件无需再完整复制一份上传缓存，回读也未另存完整副本。

另用 268,435,456 字节的新文件验证恢复：旧进程在第 0–2 片回执持久化后被 SIGTERM，新进程使用同一 uploadid（仅公开指纹，不公开原值），重验源文件及账号身份，只发送第 3–7 片，创建和完整回读双哈希通过。请求载荷合计恰为文件大小，已确认片未重发；TCP 重传未单独计量。这证明一次短时跨进程分片复用，不证明长时间停机、uploadid 过期或跨 VPS 恢复。源与回读共同校验值：

```text
1 GB MD5     3d4942b11c9614c7f918783c99754ec7
     SHA-256 b7cfc7622bd230040c7dcbfbfa58e3efd7996bd4f4ae512fc9278e824de30318
256 MiB MD5     ebd1e70aa1c1dcc7082857e00c46cbc0
        SHA-256 2f982d8098217dee82d701c7c7bcc81dfd528461731d27c10e91b7bfb419021a
```

私有隔离目录保留状态、逐片请求和成功回执；实验代码未随本次文档更新提交或发布。测试进程已停止，未创建分享或覆盖旧对象。

## 后续续传验证计划（OpenList及长期恢复待验证）

沿用既有 [Issue #3](https://github.com/bioinfo-truth/fast-transfer/issues/3) 和 [Issue #4](https://github.com/bioinfo-truth/fast-transfer/issues/4)，直接 OAuth 的短时恢复已取得上述证据；以下 OpenList 与扩展异常场景仍为待执行计划，不能视为已获准的新中断实验。

1. 在指定分片成功回执落盘后，于约 30% 上传位置受控中断。分开测试仅终止/重启 rclone（OpenList 保持运行）和终止/重启 OpenList；记录前后客户端版本、账号/应用身份指纹及同一源文件哈希。
2. 私有证据中记录 uploadid、分片索引、MD5、成功回执、请求次数和字节；公开结果仅使用脱敏任务标识，不发布令牌、签名下载地址或 uploadid。检查恢复后已确认分片是否再次发送，分别统计 WebDAV 输入重传和 VPS 到百度的分片重传量。
3. 区分服务端秒传/复用、客户端从头重传与真正复用已完成分片。成功退出、耗时减少或最终文件正确都不能单独证明续传。
4. 恢复后确认远端精确长度，并完整回读核对 MD5 与 SHA-256。AList 当前分片进度为 20 分钟内存缓存；重启服务不保证保留，不能将此期限等同于百度 uploadid 寿命。
5. 身份、源内容/版本、分片布局变化或哈希不符时停止复用；任务失效、权限/容量错误、磁盘保留线或有界流量/无进展策略触发时停止，保留证据，不自动覆盖远端或无限重试。

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
