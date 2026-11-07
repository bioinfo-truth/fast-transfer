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

真实 HTTP 绑定、账号权限/文件限制、真实禁止覆盖语义及回读仍未验收；M2 全程 5 GiB 保护与 M3 后端停止/缓冲边界在下一次同一真实任务联合验证。下一步具体文件、进程、目标、新授权范围和清理规则已写入说明，状态 pending、未尝试，并非权限或网络拒绝。整项 M2/M3 不提前标完成。

## 后续里程碑

| 项目 | 当前状态 |
| --- | --- |
| M1 输入与真实样例 | 契约、样例/来源快照和可执行测试通过 |
| M2 源下载与校验 | 源阶段已有实测；后端预算/离线测试通过；实际上传全过程空间保护待 M3，M2 整体验收未完 |
| M3 百度上传与回读 | 无凭据注入式适配与本地模拟通过；真实 HTTP 绑定/账号限制及上传回读待真实验收，整项未完成 |
| M4 受控分享/人工回填 | 未实现、未创建分享；权限研究可提前，真实分享依赖 M3 和授权 |
| M5 最小任务/失败处理 | 已有 intake/源校验及模拟 M3 隔离记录；完整工作流与恢复未实现 |
| M6 国内领取与 MVP 验收 | 未执行，需明确测试用户及发送许可 |

具体进度使用已有 M1–M6 执行清单，不重复创建任务。上一轮临时 access_token 配置许可已结束，不授权新一轮持久配置。未导入新凭据、未上传/分享、未发消息、未收费、未部署，也未恢复暂停的定时检查。

[项目首页](https://github.com/bioinfo-truth/fast-transfer/wiki) · [路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap) · [产品与架构](https://github.com/bioinfo-truth/fast-transfer/wiki/Product-and-Architecture)
