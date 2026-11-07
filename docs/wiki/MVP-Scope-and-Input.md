# MVP 范围与输入（2026-11-08）

## 当前决定

服务面向中国境内用户，首版由操作人员人工录入公开 HTTPS 生物数据文件链接或 manifest，再依次验证源下载、百度网盘上传/回读、分享交付和国内领取。先不做淘宝、支付、项目号解析、完整网站或收费。已有工具实测保留，不重复运行；跨 OpenList 服务重启的分片恢复是已知限制，不作为 MVP 前置。

## MVP 当前交付

实现见 [PR #9](https://github.com/bioinfo-truth/fast-transfer/pull/9)（[MVP 评审分支](https://github.com/bioinfo-truth/fast-transfer/tree/codex/mvp-intake-download)），尚未合并或部署。源码、输入契约、测试和证据见该分支的 README、docs/mvp-input-contract.md、docs/mvp-milestones.md、examples/ncbi-ecoli/ 和 docs/validation/mvp-source-2026-11-08.json。

M1 输入状态有 accepted、manual_review 和 rejected。必须有明确大小、至少一个源站 MD5/SHA-256、版本、公开性与再分发审核依据；缺失则不下载、转人工。受控数据、禁止分发、非法文件名/路径、带凭据或查询参数的 URL 拒绝。操作人员审核不等于外部客户可自行声明权限。

M2 源阶段只下载和校验，逐跳检查 HTTPS/DNS/重定向、连接固定到核验 IP 并保持原主机名 TLS 校验、不使用凭据或环境代理，独占创建新文件，保留至少 5 GiB 加 256 MiB 提前停止余量。大小、源站哈希不符停止。当前供操作人员串行运行，未实现多用户配额、硬截止任务监管或跨阶段崩溃恢复。

后端感知预算组件已补齐并经离线模型/模拟适配器验证：OpenList 额外最大整文件缓存、直接 API 不生成整文件副本、各阶段独立临时开销，未知开销转人工；按实际文件系统同盘合并、分盘独立保留，已登记的实际分配块抵扣已占用，防止重复计算。源下载已接入检查，上传/回读接口只经模拟，实际独立后端写入的全程 5 GiB 保护仍须 M3 联调。默认 source-only 不获得未来上传准入，不能将预算组件通过写成整个 M2 完成。详细说明见评审分支的[预算与验收矩阵](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-space-budget.md)。

真实样例为 NCBI E. coli K-12 MG1655 `GCF_000005845.2 / ASM584v2` 的压缩 FASTA，1,379,902 字节；[官方清单](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/md5checksums.txt) MD5 `c13d459b5caa702ff7e1f26fe44b8ad7`。本项目主机新实现已下载并匹配 MD5，独立计算 SHA-256 `a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255`；解压检查为 4,641,652 个碱基的真实参考序列。该 SHA-256 为本地计算值，不是官方源站摘要；本次不是海外 VPS 上传或国内领取测试。

公开性/分发依据为[官方组装记录](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000005845.2/)与 [NCBI Molecular Database Use Policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)：NCBI 自身不限制分子数据使用或分发，但存在第三方权利提示；保留来源/政策说明，不把它解释为所有内容或收费服务的无条件许可。

## M3 无凭据适配（模拟验证）

选直接 API 分片流程，源文件先重验 M2 收据、源站摘要和本地双哈希，隔离新目标、禁止覆盖，核对逐片回执、长度及完整流式回读。SpaceGuard 已接任务状态/临时文件登记及阶段/写入检查。本轮只有内存假远端，无真实 HTTP/凭据加载，live 被拒绝；没有重做历史性能或续传实验。

23 项新增离线测试覆盖同盘/分盘、失败源不发片、重名保护、源变化、异常脱敏、回读损坏、空间下降、阶段开销、停止不确认及重复启动。还将保留的 1,379,902 字节 NCBI 源文件做了一次纯本地模拟，完整回读双哈希一致。真实云端资格始终为 false；不能用模拟结果分享或交付。详见评审分支 [M3 说明与验收矩阵](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-upload-stage.md)。

HTTP 绑定与假响应审查已补齐；真实账号权限/文件限制、严格禁止覆盖语义及回读仍未验收；M2 全程 5 GiB 保护与 M3 后端停止/缓冲边界在下一次同一真实任务联合验证。下一步具体文件、进程、目标、新授权范围和清理规则已写入说明，状态 pending、未尝试，并非权限或网络拒绝。整项 M2/M3 不提前标完成。

## HTTP 协议绑定审查（仍无真实账号调用）

已补齐可注入客户端的 REST 绑定和默认关闭的 HTTPS 通道，并用假响应测试身份/容量、三阶段上传、所需片号、元数据/流式回读、URL/TLS/重定向、字节限额、固定超时和停止/脱敏。没有再次运行前轮演示或历史基准，没有真实令牌值。源/回读资格仍仅模拟，不能据此交付。

官方预上传参数表仅列 rtype 1/2/3，而创建文件列 0 冲突失败并要求两阶段一致，故严格“冲突即失败且不改名”仍缺明确依据。假 HTTP 诊断只测试文档明确的 1/1、不覆盖但可能改名，并对路径漂移报失败；它不是严格服务端能力证明。严格模式默认拒绝所有变更，实网客户端另有独立写关闭门；普通 RuntimeGrant 或诊断参数不能绕过。需要官方确认或明确替代政策后再审查放行，而不是先要求用户给令牌才能写绑定。详见[协议审查、官方来源和验收矩阵](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-baidu-http.md)。

会员类型/文档上限不是实际应用上传权限；真实账号、容量/权益、节点、5 GiB 全过程与停止延迟仍由 M2/M3 联合验收。实际调用状态 pending、未尝试，没有权限/网络拒绝事件。已完成的无凭据工程不再列为授权前置阻碍。

## 后续里程碑

| 项目 | 当前状态 |
| --- | --- |
| M1 输入与真实样例 | 契约、样例/来源快照和可执行测试通过 |
| M2 源下载与校验 | 源阶段已有实测；后端预算/离线测试通过；实际上传全过程空间保护待 M3，M2 整体验收未完 |
| M3 百度上传与回读 | 无凭据适配和 HTTP 假客户端协议测试通过；严格冲突写策略未放行，账号/上传回读真实验收未完成 |
| M4 受控分享/人工回填 | 人工回填/清单草稿及公开帮助研究的离线部分完成；真实权限、建链和内容核验未完成 |
| M5 最小任务/失败处理 | 单任务离线 M1–M4、持久状态/查看/人工检查已实现；真实接线和完整恢复未验收 |
| M6 国内领取与 MVP 验收 | 未执行，需明确测试用户及发送许可 |

具体进度使用已有 M1–M6 执行清单，不重复创建任务。上一轮临时 access_token 配置许可已结束，不授权新一轮持久配置。未导入新凭据、未上传/分享、未发消息、未收费、未部署，也未恢复暂停的定时检查。

[项目首页](https://github.com/bioinfo-truth/fast-transfer/wiki) · [路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap) · [产品与架构](https://github.com/bioinfo-truth/fast-transfer/wiki/Product-and-Architecture)

## 隔离不覆盖候选已实现（无真实调用）

新增 fake-only 候选：随机任务名配合本地持久独占目录，云端新目录 rtype=0，文件 precreate/create 一致 rtype=1；目录 fs_id/path 身份复核、返回改名即失败、会话过期/重放拒绝、提交未知不重试、保留全部原有及新增/不确定对象。查询不是无竞态原子性证明；此候选允许冲突时留下改名对象，不能声称零副本。源/远端长度、完整双哈希、空间及 stop 闸门继续复用。新增 7 项候选测试通过，真实写入仍独立关闭，模拟不获得交付资格。

保护原有资料可采用这一官方不覆盖策略候选，不再将 precreate=0 的严格零改名依据缺口作为全部工程阻碍。真实目录查询、权限/权益、节点行为和 M2/M3 联合验收仍 pending、未尝试；未来明确批准须包含新任务目录及可能改名/未知对象的保留范围，不覆盖、不删除、不分享。详见[候选实现、官方来源与残余风险](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-baidu-http.md)。

## M4/M5 本地独立部分（仍无真实动作）

已实现单任务离线编排：M1 输入指纹 → 已有 M2 源文件/收据复核 → M3 模拟及空间检查 → 人工分享回填/交付清单草稿。状态私有持久化、同任务锁、查看、重复启动拒绝，以及失败/取消/人工核查待办已补齐；中断或提交未知不会自动重试写入。不能从 JSON true 获得真实网络或交付权限。

官方帮助说明可设分享密码/有效期且分享可能被取消，但个人账号/应用实际分享资格仍未知。回填仅为未验证声明，保存文件映射、期限与链接/授权引用指纹，不保存链接原文、提取码或凭据；错映射、越界、过期均拒绝，模拟/真实交付资格始终隔离。没有创建或访问分享、发送给客户或重新下载数据。新增 8 项离线测试通过；真实 M3/M4 接线、实际建链/发送、完整恢复和 M6 国内领取仍待验收。详见[工作流、人工步骤与验收矩阵](https://github.com/bioinfo-truth/fast-transfer/blob/codex/mvp-intake-download/docs/mvp-workflow.md)。
