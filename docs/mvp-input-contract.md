# MVP v1 输入契约与验收（M1）

首版由操作人员人工录入公开 HTTPS 文件链接或 JSON manifest；不做淘宝、支付、项目号解析、客户网站或自动收费。用户只给链接时，先形成待审核输入，不立即下载。所有记录的 `reviewed` 由操作人员核对来源后填写，不是由外部客户勾选即可授予的权限；当前没有对外 intake API。

## 输入格式

规范实例见 [`examples/ncbi-ecoli/manifest.json`](../examples/ncbi-ecoli/manifest.json)。根对象仅允许 `schema_version: 1` 和 `files`；1–100 个文件；JSON 最大 1 MiB，重复键拒绝。文件允许字段：

| 字段 | 含义与要求 |
| --- | --- |
| name | 唯一文件名；ASCII 字母/数字开头，后接字母、数字、点、下划线或短横线；最长 180 字符；禁止目录、百分号、控制字符、尾随点及 Windows 保留名；大小写不敏感去重。不自动改名。 |
| url | 公开文件的稳定 HTTPS URL；仅 443 端口；禁止用户信息、查询串、片段、空白、反斜杠和非 ASCII URL。带签名或凭据的链接不纳入 v1；请提交稳定公开链接。 |
| size | 正整数，原始传输对象的字节数，例如 gzip 文件的压缩字节数；不能用解压体积或本地配置上限代替。 |
| md5 / sha256 | 至少一个源站提供的摘要，分别为 32/64 位十六进制。下载后独立计算的摘要不能冒充源站摘要。存在的摘要均须匹配。 |
| source.access | 公开性核验：public、controlled 或 unknown；v1 只接受 public。 |
| source.record_url | 官方数据记录链接。 |
| source.version | accession、版本及必要日期；不接受空值。文件变化须重新核验来源和摘要，不自动更新预期值。 |
| source.checksum_url | 官方校验值清单/页面链接。v1 由操作人员核对与文件名的对应关系，不自动解析任意网页。 |
| source.redistribution | status=reviewed、basis_url、note；操作人员记录可获取/交付依据及限制。prohibited 拒绝，unknown 或缺失进入人工审核。 |

未列出的字段拒绝，防止静默忽略 `Authorization` 等配置。来源元数据 URL 同样接受语法及字面地址检查，但 M1 不自动访问它们，也不把操作人员填写的说明当成法律保证。

## 状态和处理

| 情况 | 状态 | 行为 |
| --- | --- | --- |
| 所有必需字段通过 | accepted | 仅表示可以进入 M2；不是已下载、已上传或已交付。 |
| 大小未知、缺少源站哈希、版本/公开性/再分发依据未审核 | manual_review | 不发起下载；操作人员从官方记录补齐并重新提交。v1 不提供强制跳过校验开关。 |
| 受控访问或禁止再分发 | rejected | 不尝试登录、不读取其他凭据、不下载。 |
| 非法文件名、目录逃逸、重复名、无效大小/哈希、未知字段、非法 URL | rejected | 修正后重新提交，不自动修复输入。 |
| 源站返回 401/403 | manual_review | 停止，可能为权限或链路问题；不自动判定地域封锁，也不自动增加凭据。 |
| 下载大小/源站哈希不符、危险重定向、私网 DNS | rejected | 停止，清理本次新建的未验证文件；不替换预期摘要、不上传。 |
| 大小/磁盘预算不足、网络故障、截止时间耗尽 | manual_review | 停止并保留安全错误码；不无限重试。 |

CLI：`python3 -m fast_transfer.intake examples/ncbi-ecoli/manifest.json`，退出码 accepted=0、manual_review=2、rejected=1。只录入链接可使用 `python3 -m fast_transfer.intake --url https://example.org/sample.fastq.gz --name sample.fastq.gz`，会因缺少来源元数据而返回人工审核。输出仅含索引、安全文件名、状态和错误码，不回显 URL 或字段原值。

## M2 实施边界

`python3 -m fast_transfer.download` 是新的源文件执行入口，与旧 PoC 上传入口分开。先要求整份输入 accepted，再创建全新 0700 工作目录、逐文件独占写入 0600 文件；不覆盖旧目录、旧文件或符号链接。默认每文件 16 MiB（本次真实样例用 2 MiB 上限）；至少保留 5 GiB，并加 256 MiB 提前停止余量及独立的元数据预算。下载器已接入后端感知的空间检查组件；默认 source-only 只验证源阶段，显式后端计划才计入额外缓存/阶段开销，详情见[空间预算](mvp-space-budget.md)。真实上传期保护仍需 M3 接线及验收。小样例通过不代表适合所有大文件；当前要求人工串行运行，不支持多进程共享磁盘配额。

每次请求及每个重定向都核验 HTTPS/目标；解析结果中只要有非全球可路由或组播地址就拒绝；连接固定到已核验的 IP，同时以原始主机名做 TLS 证书验证。最多 3 跳重定向，循环、降级、凭据链接、私网目标拒绝；不读取环境代理或附加 Cookie/Authorization。没有自动故障重试。

已知输入大小，即使源站无 Content-Length 也按实际流量限制并核验；有 Content-Length 时必须一致，重复/非法长度、冲突响应定界和非 identity 内容编码拒绝。每次读取检查大小、磁盘余量及读取循环截止时间；连接/读取 socket 超时不超过 30 秒，总读取预算默认 300 秒。操作系统 DNS 解析时长和 HTTP 头部慢速传输没有独立进程级硬截止保障，不能据此承诺任意恶意源站下的绝对总时限；对外服务前需补充独立任务监管。

下载成功写入 `.receipts/<index>.json`，状态 source_verified，记录实际长度、本地 MD5/SHA-256、实际验证的源站摘要算法和重定向跳数。收据与输入文件分目录，避免合法文件名与收据冲突。正常失败只清理本次新建的未验证文件，保留已通过文件与收据；崩溃/强制终止恢复和原子任务状态属于 M5，尚未实现。后续阶段必须重新核验实际文件及收据，不能仅凭文件存在而上传。

## M1 验收证据

- 真实小样例：NCBI RefSeq E. coli K-12 MG1655 `GCF_000005845.2 / ASM584v2`；1,379,902 字节；源站 MD5 `c13d459b5caa702ff7e1f26fe44b8ad7`。
- 样例目录保留官方组装报告、MD5 清单和记录快照 SHA-256；来源及版权政策见该目录 README。未保存大二进制到仓库。
- `tests/test_intake.py` 覆盖契约及人工审核/拒绝；`tests/test_safe_download.py` 覆盖 DNS/IP 固定、危险重定向、流量和磁盘预算、哈希错误及旧文件保护，采用模拟网络，不会访问私网。
- M2 另有一次本项目主机的真实样例下载，官方 MD5 一致；证据见 [`validation/mvp-source-2026-11-08.json`](validation/mvp-source-2026-11-08.json)。这不是海外 VPS 上传、分享或境内领取验收。
