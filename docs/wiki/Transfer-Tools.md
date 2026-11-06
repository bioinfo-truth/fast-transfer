# 高速传输工具调研

调研日期：2026-11-07。仅核对公开官方资料，未申请试用、联系销售、安装新工具或实测性能。下面的适配判断是基于文档的工程推断，不是性能结论。

## 与本项目的关系

将链路拆为公开数据库到工作节点、海外到境内自有节点、百度网盘上传与交付三段。高速协议通常要求对应服务端、客户端或网关；任意 HTTPS 源站和百度网盘不会因为我方安装加速工具就原生支持该协议。第三方工具不能保证解决 API 的 HTTP 403、账号权限或分享权限问题。

## 候选比较

| 工具 | 文档确认能力 | 适合项目的环节 | 限制与待验证 |
| --- | --- | --- | --- |
| 镭速文件传输 | Linux/命令行/API/SDK、自有存储与部分云存储、恢复与同步 | 自有海外节点与境内 NAS 间迁移 | 两端部署、UDP 可达、许可证与基础设施费用；未找到百度网盘原生连接器证据 |
| 镭速 Proxy | HTTP、CONNECT、SOCKS 代理接入，两端 Proxy 间使用自研协议转发 | 境内主机经海外出口获取数据，或海外工作节点经另一个可用出口调用百度 | 两端代理组件与可用出口仍需提供；不自动扩大网盘权限，也不保证消除 403；需核实小 VPS 资源及商业授权 |
| IBM Aspera / ascp | FASP、命令行、恢复；ENA 官方明确提供 Aspera 下载方式 | ENA 支持的公开文件到 VPS 或境内工作节点 | 只适用于来源实际提供的 Aspera 端点；客户端许可及商业代下载适用范围需确认；自建服务端另行计费 |
| Signiant Jet | 自动化点对点路由、自有或云存储；每路由两端 connector | 后期自有节点间的大批量自动传输 | 年订阅、销售报价；不能假定任意数据库 URL 与百度网盘即为可用端点 |
| Globus | 科研数据集合与端点间托管传输，支持本地和若干云存储连接器 | 数据来源已经有 Globus 集合时接入 | 并非任意 URL 下载器；商业服务使用条件应向 Globus 核实，不能套用非营利研究免费条件 |
| aria2 | HTTP(S)/FTP 等来源、多连接分段、续传和校验 | 普通公开 URL 下载的低成本基线 | 受源站 Range、限流和网络路径影响；不直接上传百度网盘，也不自动解决小磁盘全文件暂存 |
| SRA Toolkit | prefetch 获取 SRA 及恢复未完成下载，转换 FASTQ | SRA 数据源适配与下载 | 不是通用跨境链路加速器；格式转换额外占用 CPU 和磁盘 |

## 镭速的两种部署应分开评估

文件传输服务适合双方已有文件的节点间搬运。Proxy 可让现有 HTTP/SOCKS 客户端经由加速通道转发，数据源不必安装镭速，但我方仍需在适当位置部署客户端和服务端，链路分成数据库到出口及出口到工作节点等阶段。对百度网盘可尝试只代理控制请求、数据请求直连，是否可行仍需小文件实验。

完整镭速服务端公开部署指南建议 4 核 CPU、8 GB 内存、至少 40 GB 磁盘，高于当前小型测试 VPS。该要求不应直接套用到独立 Proxy；需向厂商确认 Proxy 在 1 核、2 GB、30 GB 环境的要求和目标吞吐。厂商“百倍加速”等宣传不能当成本链路保证。

## 费用

- 国内镭速价格页要求咨询 License 方案，未给出本项目可直接采用的人民币报价。专业版表中列有 200 Mbps 和 100 GB 下载流量，流量周期及实际授权范围应确认。
- 国际官网当日列出 Cloud 99 美元/月（1 TB 存储、2 TB 传输/下载流量）和 SMB 1,599 美元/年（自部署、标称不限制传输量）。这些不是 Proxy 的报价，也不能视为国内采购报价；软件不计量不代表云服务器和运营商流量免费。
- Signiant Jet 按年订阅与 connector/route 组织授权，需报价。Globus 商业使用及连接器另核。Aspera 源站客户端下载与购买自建服务端不是同一授权。
- 综合成本记录：软件许可、带宽与云出口、两端服务器/存储、运维、重试及每个成功交付 TB。FASTQ.gz 等已压缩文件不应默认能再显著压缩。

## 建议优先级与验证

1. 优先比较普通 HTTPS 下载基线（curl/aria2）与 ENA 官方 Aspera 下载；保持相同文件、节点和校验，按服务条款设置有限并发。
2. 百度网盘控制 API 和分片数据上传分别测量。当前 VPS 的预上传 403 先排查；高速文件协议不是权限或可达性修复的证明。
3. 仅在证据显示自有海外到境内链路是瓶颈时，申请镭速 Proxy 或文件传输试用；先核对目标架构、资源、费用和商业转售/代下载许可，再部署。
4. Signiant 与 Globus 保留为后期或特定数据源候选，不预先采购。
5. 测试覆盖持续有效速度、首字节与控制请求时延、中断恢复、重传字节、峰值磁盘和总费用。商业方案应与相同网络的免费基线比较；试用前先设预算，不发布未经验证的速度承诺。

## TeraBox：候选存储与交付后端

2026-11-07 核对官方集成页面与 API 文档，尚未申请集成应用或实测。作为候选网盘后端，不改变百度网盘主交付方向。

- 官方有授权、预上传、分片上传及创建文件（服务端合并）接口。预上传需要分片 MD5 列表，因此不能直接认定支持未知内容无限流式上传；两遍读取或有界暂存仍待验证。
- 需通过 `/oauth/tokeninfo` 获取 `api_domain` 和 `upload_domain`，文件操作受应用目录约束。不能复用百度令牌或假定接口完全兼容，应单独适配。
- 官方介绍分享能力，文档列出分享验证、列表、转存、下载接口；自动创建交付分享链接的接口及权限仍待确认。
- 海外云端缓冲或替代交付渠道均为候选。境内无需代理的登录、领取分享及持续下载速度，收件人是否必须注册或付费，尚未验证。海外上传成功不能证明境内交付快；作为缓冲再转百度会增加一次搬运。
- 应用申请资格、商业代下载使用条件、API 配额、分片有效期、跨进程恢复、API 单文件限制和费用待确认，不能将客户端会员额度直接套用于 API。

建议先验证美国节点上传公开小文件、境内普通网络领取下载并校验；再测代表性大文件、中断恢复、峰值磁盘，区分发送方和接收方的会员条件，记录成功交付时间与每 TB 总成本。暂不采购会员或替换交付链路。

依据：[官方集成介绍](https://www.terabox.com/integrations)、[官方 API 文档](https://www.terabox.com/integrations/docs)。以上是文档能力，不是账号权限或性能实测结论。

## Send Anywhere：人工临时传输候选，暂不作为自动化主链路

2026-11-07 核对官方资料，未实测。最关键变化是官方宣布于 2026-03-31 终止 Open API 服务，原 API key 失效；普通用户服务继续。旧 API 页面或历史 SDK 文章不能作为仍可集成的依据。

- 六位码方式即时发送、不在服务器持久保存文件，要求发送端配合接收端在线；官方单次上限为 50 GB。不宜直接假定其连接在本链路必定为点对点或必定高速。
- 分享链接先上传到平台，默认保留 48 小时。官方帮助页列出每链接免费/Lite/Standard 上限分别 10/20/30 GB、最多 1,000 个文件；接收方完成下载需文件上传完成。
- 帮助页列出每账号每月分享下载流量免费/Lite/Standard 为 10/200/500 GB，另有链接存储容量限制。此类消费级额度不适合作为批量 TB 级交付的默认配置；采购前应重新核对实际套餐。
- 官方有 Linux 桌面下载，当前列出 Ubuntu 24.04 或以上；不能据此认定提供受支持的无界面 CLI 或 Debian 自动化服务。
- 可保留为人工小批量临时交付、海外节点到境内 NAS 传输的实验候选。境内可达性、速度、恢复能力均未实测，也没有证据表明可直接上传百度网盘或减少下载源文件的暂存空间。除非获得厂商当前支持的自动化方案，否则不投入旧 Open API 集成。

依据：[Open API 终止公告](https://support.send-anywhere.com/hc/en-us/articles/54660040864025-End-of-support-for-Open-API-Service-26-3-31)、[单次大小限制](https://support.send-anywhere.com/hc/en-us/articles/360005223534-File-size-that-can-be-transferred-at-one-time)、[文件保留方式](https://support.send-anywhere.com/hc/en-us/articles/360005222894-How-long-the-transferred-files-are-kept-on-the-server)、[下载流量及链接限制](https://support.send-anywhere.com/hc/en-us/articles/360003454153-I-am-unable-to-download-files-from-the-link)、[官方下载](https://send-anywhere.com/file-transfer)。

## 官方依据

- [镭速 Proxy](https://www.raysync.cn/products/vpn/)
- [镭速国内价格](https://www.raysync.cn/pricing/)
- [镭速国际价格](https://www.raysync.io/pricing/)
- [镭速部署与存储文档](https://www.raysync.io/support/document/product/export/)
- [ENA 文件下载和 Aspera](https://ena-docs.readthedocs.io/en/latest/retrieval/file-download.html)
- [IBM Aspera](https://www.ibm.com/products/aspera)
- [Signiant Jet 价格与路由授权](https://www.signiant.com/products/jet/pricing-packaging/)
- [Globus 商业订阅 FAQ](https://docs.globus.org/faq/subscriptions/)
- [Globus 订阅与来源集合说明](https://www.globus.org/subscriptions/inquiry-filter)
- [aria2 官方手册](https://aria2.github.io/manual/en/html/aria2c.html)
- [NCBI SRA 下载说明](https://www.ncbi.nlm.nih.gov/sra/docs/sradownload/)
