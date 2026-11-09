# Fast Transfer 项目 Wiki

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

已追踪 Cookie UK、贴吧 UID/现有 OAuth 的不同通道以及按 path_list 建链；新方案要求严格身份/预期账号与精确对象绑定，默认 unavailable 的可注入适配器和一次意图/unknown 核查，尚未实现或开启真实访问。实际固定源码的假响应特征测试两个顶层/十二子场景通过，确认 UK 可接受缺 errno/非正 uk、ShareSet 可接受缺成功码/ID 或非法链接等宽容缺口，不能当作安全或服务能力通过。编译需显式 -vet=off 避开已有无关路径诊断，未宣称默认 vet 通过。

现有 Xtransfer 对象访问、客户端 Cookie 契约/商用支持仍未验证；既有站点拒绝有效，先确认可验证的允许渠道，之后再分别审阅精确主机/构建、短期只读身份/对象、单次建链与清理范围。无真实秘密、账户请求或链接生成。见[源码依据、适配器契约和阶段方案](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-identity-share-plan.md)。


### 严格验证层实现与十五项测试完成

原 UK/ShareSet 缺口已形成独立 Go 候选响应验证层及 fixture-only 单意图账本，格式/编译/vet 和十五项受限运行测试通过，涵盖 JSON/身份/精确对象/期限绑定、规范 URL、未知不重试、映射冲突隔离与停止重放。原解析函数和真实入口未被打开或自动替换，无凭据/provider/账户请求/新依赖；候选 Principal/映射输入不算服务认证。

本组件的无凭据测试范围已完成。M4.3/M4.4 真实验证仍缺允许渠道依据和可信 Cookie 身份/指定 Xtransfer 对象/分享内容映射契约，不能用模拟或换工具推定放行。精确后续阶段范围见[接入方案](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-identity-share-plan.md)，实现/测试见[适配层说明](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/patches/baidupcs-go-v4.0.2/adapter/README.md)。


### 真实验证进入条件收敛（2026-11-09）

严格候选验证层已实现，十五项隔离测试是已有结果，本次未重复测试。生产可信接线与真实分享仍未完成。原浏览器导航拒绝只有可信转述，缺控制提供方名称、策略引用及适用范围；拟议 Cookie 账户请求尚未尝试，不能写成百度 API 已拒绝。下一步先取得原访问控制提供方或管理者的非敏感范围说明及允许复核途径，不索取 Cookie、不换工具探测。详见[当前进入条件与候选阶段范围](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/pcs-real-test-readiness.md)。
