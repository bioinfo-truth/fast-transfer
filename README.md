# fast-transfer：公开生物数据代下载 MVP

面向中国境内用户，提供海外公开HTTPS数据的代下载和百度网盘交付。首版由操作人员人工录单、审核manifest、串行执行、官方API上传与完整回读、境内原生分享，并记录本人领取；淘宝、支付、项目号解析、多用户并发和无限流式传输不作为前置。

通用任务已完成两次真实交付：902,395字节蛋白文件，以及834,262,758字节鼠基因组＋7,187字节报告，均完整MD5/SHA256回读、一次分享并由本人确认下载。原地OAuth与国内原生登录复用；固定Go SDK承担请求编码，项目保留摘要、资源预算和持久恢复控制。故障证据与完整验收缺口持续列在[验收状态](docs/mvp-acceptance-status.md)，不将模拟测试或单次成功当作整体完成。

- [操作手册：人工队列、录入、执行、恢复、交接与保留](docs/operator-runbook.md)
- [输入契约](docs/mvp-input-contract.md)、[通用任务](docs/mvp-task-entry.md)、[上传与恢复](docs/mvp-task-upload.md)
- [只读未知合并核查](docs/unknown-commit-inspection.md)、[私有交付收据](docs/private-delivery.md)
- [SDK复用](docs/official-sdk-reuse.md)、[编码适配](docs/sdk-request-encoder.md)、[运行包](docs/versioned-runtime.md)
- [蛋白真实任务](docs/protein-pilot-2026-11-11.md)、[鼠多文件真实任务](docs/mouse-pilot-2026-11-11.md)、[源/令牌/空间故障](docs/source-token-faults-2026-11-11.md)
- [项目 Wiki](https://github.com/bioinfo-truth/fast-transfer/wiki)、[路线图](https://github.com/bioinfo-truth/fast-transfer/wiki/Roadmap)

## 本地只读入口

在已审核仓库、仅使用标准库：

```sh
python3 -B -m fast_transfer.intake examples/ncbi-ecoli-protein/manifest.json
```

accepted只表示输入通过，不是授权或已交付。VPS使用经过核对的独立运行包和显式私有路径；完整命令见操作手册。单文件默认1GiB、4MiB片、每manifest最多100文件，逐文件核验后才可清理；实际空间保留5GiB底线及余量。更改任务设置需重新审核，不改变既有快照。没有固定速度或商业SLA承诺。

## 检查

在Linux且libseccomp可用、实际SDK helper已按文档构建后，运行已审核的明确测试模块；不要用广泛discover夹带本地未提交实验：

```sh
python3 -I -S -B tests/support/run_workflow_isolated.py \
  test_task_recovery test_stability test_intake test_safe_download test_space \
  test_stop_boundaries test_baidu_md5 \
  test_resources test_task_upload_process test_task_retry test_task_inspect \
  test_task_delivery test_delivery test_task_handoff test_task_cleanup \
  test_task_upload test_task test_baidu_protocol test_sdk_codec
```

该入口用继承性内核禁网、空环境与临时HOME执行测试，合成响应不冒充云端成功；真实验收单独记录。Go helper构建和检查见SDK文档。历史`python3 -m fast_transfer`、M3模拟器、M4/M5离线聚合器及M6早期准备材料保留作对照；实际人工录单使用通用Task链路，不以旧PoC处理客户链接。
