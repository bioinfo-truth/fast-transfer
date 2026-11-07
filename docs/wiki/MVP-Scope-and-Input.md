# MVP 范围与输入（2026-11-08）

## 当前决定

服务面向中国境内用户，首版由操作人员人工录入公开 HTTPS 生物数据文件链接或 manifest，再依次验证源下载、百度网盘上传/回读、分享交付和国内领取。先不做淘宝、支付、项目号解析、完整网站或收费。已有工具实测保留，不重复运行；跨 OpenList 服务重启的分片恢复是已知限制，不作为 MVP 前置。

## M1/M2 当前交付

实现位于 [MVP 评审分支](https://github.com/bioinfo-truth/fast-transfer/tree/codex/mvp-intake-download)，尚未部署。源码、输入契约、测试和证据见该分支的 README、docs/mvp-input-contract.md、docs/mvp-milestones.md、examples/ncbi-ecoli/ 和 docs/validation/mvp-source-2026-11-08.json。

M1 输入状态有 accepted、manual_review 和 rejected。必须有明确大小、至少一个源站 MD5/SHA-256、版本、公开性与再分发审核依据；缺失则不下载、转人工。受控数据、禁止分发、非法文件名/路径、带凭据或查询参数的 URL 拒绝。操作人员审核不等于外部客户可自行声明权限。

M2 仅下载和源校验，逐跳检查 HTTPS/DNS/重定向、连接固定到核验 IP 并保持原主机名 TLS 校验、不使用凭据或环境代理，独占创建新文件，保留至少 5 GiB 加 256 MiB 提前停止余量。大小、源站哈希不符停止。当前供操作人员串行运行，未实现多用户配额、硬截止任务监管或跨阶段崩溃恢复。

真实样例为 NCBI E. coli K-12 MG1655 `GCF_000005845.2 / ASM584v2` 的压缩 FASTA，1,379,902 字节；[官方清单](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/md5checksums.txt) MD5 `c13d459b5caa702ff7e1f26fe44b8ad7`。本项目主机新实现已下载并匹配 MD5，独立计算 SHA-256 `a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255`；解压检查为 4,641,652 个碱基的真实参考序列。该 SHA-256 为本地计算值，不是官方源站摘要；本次不是海外 VPS 上传或国内领取测试。

公开性/分发依据为[官方组装记录](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000005845.2/)与 [NCBI Molecular Database Use Policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)：NCBI 自身不限制分子数据使用或分发，但存在第三方权利提示；保留来源/政策说明，不把它解释为所有内容或收费服务的无条件许可。

## 后续里程碑

| 项目 | 当前状态 |
| --- | --- |
| M1 输入与真实样例 | 契约、样例/来源快照和可执行测试通过 |
| M2 源下载与校验 | 本地实现、模拟异常测试和一次真实小文件源下载通过 |
| M3 百度上传与回读 | 新 MVP 轮未执行，尚需适配和具体用途授权；旧工具结果不替代验收 |
| M4 受控分享/人工回填 | 未实现、未创建分享；权限研究可提前，真实分享依赖 M3 和授权 |
| M5 最小任务/失败处理 | 已有 intake/源校验状态；完整持久化恢复未实现 |
| M6 国内领取与 MVP 验收 | 未执行，需明确测试用户及发送许可 |

具体进度使用已有 M1–M6 执行清单，不重复创建任务。上一轮临时 access_token 配置许可已结束，不授权新一轮持久配置。未导入新凭据、未上传/分享、未发消息、未收费、未部署，也未恢复暂停的定时检查。

[项目首页](https://github.com/bioinfo-truth/fast-transfer/wiki) · [路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap) · [产品与架构](https://github.com/bioinfo-truth/fast-transfer/wiki/Product-and-Architecture)
