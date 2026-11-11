# fast-transfer：公开生物数据代下载 MVP

目标链路是人工录入公开 HTTPS 文件链接/manifest → 下载及源站校验 → 上传百度网盘并核验 → 分享交付 → 中国境内用户领取校验。首版不做淘宝、支付、项目号解析、完整网站或收费。

当前已完成一次真实公开小样例的官方API上传和完整双哈希回读；用户已确认境内原生BDUSS/STOKEN登录、原文件核对、分享及未登录领取下载成功。这是单样例闭环，不等于通用MVP已完成。通用任务真实接线、后端全过程空间/取消保护和跨阶段恢复仍待验收。官方Go SDK复用已固定版本并通过5项禁网兼容性测试，尚未替换现有上传后端。具体见[下一步MVP清单](docs/mvp-next-steps.md)和[SDK复用边界](docs/official-sdk-reuse.md)；下文部分旧阶段说明保留历史实现范围，不代表当前样例仍未交付。

- [通用任务入口：持久状态、源下载和恢复（上传尚未接入）](docs/mvp-task-entry.md)
- [输入契约与拒绝/人工审核规则](docs/mvp-input-contract.md)
- [百度 HTTP 绑定、官方依据与关闭门](docs/mvp-baidu-http.md)
- [M3 无凭据适配、模拟状态与真实验收边界](docs/mvp-upload-stage.md)
- [后端空间预算、检查接口与未验证范围](docs/mvp-space-budget.md)
- [M1–M6 里程碑与授权边界](docs/mvp-milestones.md)
- [真实 NCBI 样例及来源/使用政策](examples/ncbi-ecoli/README.md)
- [项目 Wiki](https://github.com/bioinfo-truth/fast-transfer/wiki)（[仓库镜像](docs/wiki/Home.md)）

## 只读运行

Python 3.10+，仅标准库，无需网盘凭据：

```sh
python3 -m fast_transfer.intake examples/ncbi-ecoli/manifest.json
python3 -m fast_transfer.download examples/ncbi-ecoli/manifest.json --output-dir ./scratch-ncbi-new-run --max-file-bytes 2097152
```

输出目录必须不存在；源文件逐个下载，收据位于 `.receipts/`，不会上传或分享。默认单文件上限 16 MiB；工作文件系统至少保留 5 GiB，另加 256 MiB 提前停止余量，以及独立的源收据/元数据预算。默认 source-only 计划不含未来后端空间保证；选择后端计划时须显式提供开销及目录，命令仍不会上传。当前只供操作人员串行运行，不具备多用户配额和完整任务监管。

只给公开链接也可以先录入，例如：

```sh
python3 -m fast_transfer.intake --url https://example.org/sample.fastq.gz --name sample.fastq.gz
```

缺少大小、源站哈希或来源审核记录时返回 `manual_review`（退出码 2），不会开始下载。`accepted`（0）仅代表输入通过；`rejected`（1）需修正或拒绝。不接受受控访问、带凭据/查询参数的链接、私网目标或危险重定向。详见输入契约。

历史 `python3 -m fast_transfer` 是旧 PoC 入口，保留用于对照，**不用于 MVP 的用户链接处理**；其输入和下载安全实现不具备新契约，不应作为服务接口。[历史 PoC 说明](docs/legacy-poc.md)与未提交实验材料保持独立。

## 检查

```sh
python3 -m unittest discover -s tests -v
```

新测试使用模拟网络检查危险输入、重定向、固定 IP 与 TLS 主机名、大小/磁盘/哈希错误及旧文件保护。另有一次真实 NCBI 小文件源下载记录，见 [M2 证据](docs/validation/mvp-source-2026-11-08.json)；它不包含网盘上传、分享或客户领取。

M3 的 `python3 -m fast_transfer.m3 --simulate ...` 仅使用本地已校验文件与内存假远端，不加载凭据或连接网盘；没有 live 回退。模拟成功始终 `cloud_verified=false`、`delivery_eligible=false`，不得用于真实分享。操作及完整验收矩阵见 M3 说明。

新增 fake-only [隔离不覆盖候选](docs/mvp-baidu-http.md)：目录身份核验、改名失败保留、提交未知不重试；真实写入保持关闭。

[M4/M5 离线单任务工作流](docs/mvp-workflow.md)：人工回填与清单草稿、私有状态/查看及人工核查；无真实分享、发送或交付能力。

[M6 本地验收准备](docs/mvp-acceptance.md)：回执契约、只读文件核验与真实领取清单；准备完成不代表境内实测通过。

[单次获准真实样例与同目录续办](docs/mvp-live-sample.md)：真实上传/完整回读已通过，分享创建仍待既有能力核实或人工建链；未通过境内领取验收。
