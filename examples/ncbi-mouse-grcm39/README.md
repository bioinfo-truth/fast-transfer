# GRCm39代表性文件：已准备，未执行

2026-11-11。用于小任务闭环之后的大文件/不同manifest与多文件串行验收。只做了匿名官方目录阅读、HEAD大小及MD5清单核对，没有下载载荷、创建实际任务或新建百度对象。原成功样例不重放。

来源为[NCBI GRCm39目录](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/635/GCF_000001635.27_GRCm39/)，[官方MD5清单](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/635/GCF_000001635.27_GRCm39/md5checksums.txt)已保存快照/摘要。公开非人鼠参考序列与注释按[NCBI Molecular Data Usage](https://www.ncbi.nlm.nih.gov/home/about/policies/#data)做本次有界传输审核，保留出处和第三方权利提醒；不是任意商业分发资格保证。

| 顺序 | manifest | 大小/分片 | 目的 |
| --- | --- | --- | --- |
| 1 | manifest-genome-and-report.json | FASTA 834,262,758字节＋报告7,187字节，8MiB片100＋1 | 先完成近1GB，再验证同一任务目录第二文件及逐文件清理/空间复用 |
| 2 | manifest-genbank.json | GenBank 1,133,653,005字节，8MiB片136 | 不同manifest及超过默认1GiB上限的明确任务配置 |

## 已核对预算

第一组单文件上限1GiB，第二组显式2GiB；都使用8MiB片、最多1024片。第二组在默认1GiB限制下确实拒绝，不能省略`--max-file-bytes`。manifest intake和TransferLimits验证通过，不是账号资格/上传许可探测。

保守规划按5GiB底线＋256MiB余量＋最大单文件＋两份64MiB元数据 allowance＋1MiB源开销计算：第一组约6.61GB、第二组约6.91GB。此为偏保守规划，不替代SpaceGuard逐阶段检查。VPS本次观测可用24,289,931,264字节。

8MiB的SDK内存准入估算加余量402,653,184字节，本次VPS可见可用1,760,395,264字节；不代表实际RSS硬上限。实际执行前仍须新鲜账号/容量/允许分片大小核查，8MiB不能仅凭既有小文件成功推断可用。

只计源下载＋上传＋完整回读的净载荷网络量，约2.50GB和3.40GB，另有协议/重试开销。串行运行，核验后清理前一个本地载荷，不预取另一大文件。不能根据0.9MB历史样例的18.4秒推算这两组耗时。

## 下一轮执行/失败接续

1. 使用已部署运行版本与原地既有OAuth，创建新的独立任务，保存manifest/设置摘要；不得改旧成功任务。示例配置：

```sh
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS create \
  examples/ncbi-mouse-grcm39/manifest-genome-and-report.json \
  --max-file-bytes 1073741824 --part-bytes 8388608
```

2. 先源下载和独立大小/MD5/SHA256校验，记录资源采样。源站中断仍是完整源恢复或明确不完整源重启，不承诺Range字节续传。
3. 通过可信测试调用器在首片**确认回执持久后**停止一次执行，保存私有退出证据；源/会话/首片保留。随后新进程沿用同一Task接续，确认目录/预上传/首片不重发，完整回读成功后再清理。没有在HTTP调用中途刻意制造未知写入。
4. 每次上传/回读执行最大900秒。超时检查真实进程/句柄及任务状态，不能因为观察超时启动第二个worker；确认的片可接续，未知操作先停。唯一未知commit只读核查，其他未知当前转人工，不改数据库清空意图。
5. 第一大文件完整核验/清理后，再执行报告文件；全部完成后才导出v2清单、原生meta和一次随机码分享。分享失败不重传数据，领取确认独立记录。
6. 第一组证据通过后再创建第二组（上限2GiB，8MiB片），不直接并发下载两组。本次尚未执行以上真实步骤。

机器可读计划见budget.json，来源记录见source-record.json；目标是接近/超过1GB的验收准备，不能称为已完成数GiB大文件/真实故障全部验收。
