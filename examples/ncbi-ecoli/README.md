# 小型真实生物数据验收样例

NCBI RefSeq 的 E. coli str. K-12 substr. MG1655 参考组装：`GCF_000005845.2 / ASM584v2`，组装日期 2013-11-03，BioProject PRJNA225。不是人工生成的测试载荷，也不涉及受控人类样本。

- [官方组装记录](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000005845.2/)
- [原始压缩 FASTA](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_genomic.fna.gz)
- [官方 MD5 清单](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/md5checksums.txt)
- [官方组装报告](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_assembly_report.txt)
- [NCBI 使用政策，尤其 Molecular Database Use Policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)

2026-11-08 核对匿名 HTTPS 可读性、文件 Content-Length 1,379,902 和官方 MD5 `c13d459b5caa702ff7e1f26fe44b8ad7`。目录中的 md5checksums.txt、assembly_report.txt 是对应公开元数据快照；source-record.json 记录来源、版本、观察值和快照 SHA-256。manifest 中的 MD5 是源站值；后续计算的本地 SHA-256 不冒充官方校验值。若源站文件/清单变化，应人工审查，不能自动改成最新值后宣称复现成功。

NCBI 表示自身不限制分子数据库数据的使用或分发，不接受提交者要求限制再用/再分发的数据；同时指出提交者或来源国可能主张知识产权，NCBI 不提供第三方权利的无条件许可。此例以公开非人类参考序列和该政策作为有限测试/交付的审核依据，保留来源、NCBI 致谢和政策提示；不代表对所有 NCBI 内容或后续收费服务完成权利审查。发现具体权利限制时停止并转人工处理。

运行只读验收：

```sh
python3 -m fast_transfer.intake examples/ncbi-ecoli/manifest.json
python3 -m fast_transfer.download examples/ncbi-ecoli/manifest.json --output-dir ./scratch-ncbi-new-run --max-file-bytes 2097152
```

输出目录必须不存在；工作文件系统须满足文件预算、5 GiB 预留及 256 MiB 余量。命令只下载/校验源文件，不上传、不创建分享、不发送消息。源文件保留在工作目录，收据在 `.receipts/0.json`。仓库不包含该 FASTA 二进制。
