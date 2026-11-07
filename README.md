# fast-transfer：公开数据下载与网盘上传 PoC

项目总览、验证状态和架构见[项目 Wiki](https://github.com/bioinfo-truth/fast-transfer/wiki)（[仓库镜像](docs/wiki/Home.md)），执行进度使用 [GitHub Issues](https://github.com/bioinfo-truth/fast-transfer/issues) 跟踪。

第一阶段以文件清单作为输入，逐个下载公开 HTTPS 文件，按需验证源站 MD5，然后通过百度网盘开放平台的预上传、分片上传和创建文件接口上传到自己的应用目录。一个文件完成后才处理下一个，限制文件大小并为系统磁盘保留空间。输出 JSON Lines，可留存计时和文件校验记录。

## 当前范围

- 一个进程顺序处理文件，避免项目总大小占满磁盘。文件必须能放入磁盘预算；暂不支持超过磁盘容量的双遍读取。
- 独立实验已通过 AList + rclone 的 1 GB 上传、远端长度及完整回读双哈希验证；5 GB 同样通过上传、远端长度及完整回读双哈希验证，结果见项目总览。这不表示本仓库 Python PoC 已通过同规模测试。`--download-only` 用于先验证源站和磁盘。
- 未实现分享链接、淘宝接入、项目号解析、重试或断点续传。失败时临时文件会清理，重跑从头下载；已上传同名文件可能导致冲突，应先核对目标目录。
- 非多进程安全：不要对同一磁盘运行多个任务，直至实现共享磁盘配额。无流量上限或费用控制，请自行监控。
- 完整性：本地文件的 MD5 可与数据源清单核对；上传分片返回值与本地分片核对，并验证创建结果大小。此处描述本仓库 Python PoC 的校验能力；独立 AList + rclone 实验的回读证据见项目总览。百度云端断点续传仍未验证。
- 上传使用 4 MiB 分片。百度接口对账号、应用目录、单文件大小等存在限制；默认每文件最大 10 GiB 只是本程序本地限制，不代表账号可以上传该大小。

## 准备清单

创建 `manifest.json`，只填写可信、公开且允许获取的数据源；MD5 和 size 应来自官方清单。大小单位为字节：

```json
{"files": [{"name": "sample.fastq.gz", "url": "https://example.org/sample.fastq.gz", "size": 123456, "md5": "源站提供的32位MD5"}]}
```

`size` 和 `md5` 可省略；省略 MD5 时输出会标明未验证源站校验值。文件名必须唯一且不包含目录。

## 运行

Python 3.10+，仅使用标准库：

```sh
python3 -m fast_transfer manifest.json --work-dir ./scratch --remote-dir /apps/你的应用名/test --max-file-gib 10 --reserve-gib 5 --download-only
```

上传需要先通过百度网盘开放平台申请应用、开通上传权限并授权自己的网盘。令牌通过安全方式设置到环境变量 `BAIDU_ACCESS_TOKEN`（不要写入清单、仓库或终端历史），然后去掉 `--download-only`：

```sh
python3 -m fast_transfer manifest.json --work-dir ./scratch --remote-dir /apps/你的应用名/test --max-file-gib 10 --reserve-gib 5
```

记录输出时请避免泄露源站可能包含凭据的地址。创建远端目录及分享链接目前需要在授权允许的方式下另行处理。任务目录使用临时文件并在退出时清理；强制终止可能遗留 `fast-transfer-*` 目录，检查后手动清理。

## 插件方向

后续解析插件统一输出上述 `files` 清单和项目、样本、文件之间的映射；执行层不直接依赖 GEO、ENA 或 SRA 的解析逻辑。只有文件类型、范围及预计体积明确后才启动传输。

## 测试

```sh
python3 -m unittest discover -s tests -v
```
