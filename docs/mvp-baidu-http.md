# M3：百度 HTTP 协议绑定与无凭据审查

本轮补齐了 `baidu_protocol.py` 的 REST 请求/响应绑定和 `baidu_http.py` 的受门控、可注入 HTTPS 客户端，用假响应验证协议，不再把“写 HTTP 绑定”列为须先获得令牌批准的工作。没有读取真实授权文件、没有配置令牌、没有真实账号请求或上传/回读。现有模拟 CLI 仍只有 --simulate，所有模拟结果真实资格均为 false。

## 已核实的官方依据（2026-11-08）

旧短链接当前可能落到平台简介；本轮使用实际有接口内容的规范页面。下表是公开文档核查，不是账户权限/接口实际响应验证。页面 URL 与抓取文本 SHA-256 记在本轮证据 JSON；没有将整页正文或示例令牌复制进仓库。

| 依据 | 对绑定的影响 |
| --- | --- |
| [能力说明][ability]、[分片上传][part] | 公开上限随普通/VIP/SVIP 变化，分片数不超过 1024；分片使用获取的上传域名和 multipart。公开文档的 GB/MB 只作保守十进制参考；单位/账号实际权益边界未实测，未知/不满足时停止，不放宽上限。 |
| [预上传][precreate] | path、size、哈希列表及 autoinit；响应给 uploadid 和需上传片号。单片空列表按官方说明等价片 0；多片空列表/无效索引/未知 return_type 停止。 |
| [获取上传域名][host] | locateupload 绑定 path/uploadid，固定 appid=250528、upload_version=2.0；不固定写死示例上传节点。返回目标须 HTTPS、受信域名且无附加路径/查询；不安全即停止。 |
| [创建文件夹][mkdir] | 明确目录 rtype=0 冲突失败；绑定要求响应路径不变且 isdir=1。 |
| [创建文件][create] | 明确文件 rtype=0 失败、1 重命名、3 覆盖；要求与预上传策略一致。绑定不使用覆盖或多版本策略，且检查返回路径/长度/fs_id/isdir。 |
| [用户信息][uinfo]、[容量][quota] | 校验 uk 指纹、vip_type；容量按 total-used 计算，不能把 free（免费容量）冒充总剩余；过期/未知字段停止。userinfo 成功不等于上传权限已开通。 |
| [文件信息][metas]、[下载][download] | fsids 请求取得 dlink，校验条目身份/路径/长度。首次直链需鉴权及 pan.baidu.com UA；后续跳转不转发鉴权。云端 MD5 不替代完整回读本地双哈希。 |

## 严格冲突策略：默认 fail-closed，不能用假响应证明服务端能力

[预上传][precreate] 参数表只列 rtype 1/2/3；[创建文件][create] 列出 0 并要求两阶段策略一致。因此，本轮**不能证明 precreate/create 同用 0 的“冲突立即失败、目标绝不改名”契约**。没有用文档未列出的 0 编造成功 fixture，也不靠“先 list 再 create”的竞态检查宣称原子独占。

文档明确的 1/1 表示不覆盖旧文件，但冲突可能另建重命名对象。此语义不能自动替换 MVP 原先严格的目标冲突契约。本轮仅在 `fake-http` 客户端下，显式 `diagnostic_rename_policy=True`，测试这一已公开的协议：两阶段都为 1，禁止 is_revision，任一响应改名则整个任务失败、不交付。即使假响应未改名，也不记成严格服务端语义已证明。

严格模式默认在任何远端变更之前返回 protocol_strict_conflict_unproven。真实 HTTP 客户端还有独立实网写关闭门：即使提供显式 RuntimeGrant，也不发送 POST/分片上传；诊断开关不能对该客户端生效。这个门不是靠再给一个令牌即可绕过。

解决顺序：先取得预上传 0 的正式语义依据，或明确决定接受“仅重命名、不覆盖，但改名即失败且保留新对象”的替代语义，再审查对应放行代码。若要用隔离真实冲突实验补证据，必须单独批准测试对象/允许变更/保留范围，不能借常规文件上传授权擅自验证覆盖行为。当前既没有实测证明，也没有权限/网络拒绝事件。

## HTTP 与运行时边界

- RuntimeGrant 默认关闭；严格布尔开关、单文件目标、账号/源指纹、批准引用及不超过 15 分钟的进程内有效期均须显式满足。它是操作人员声明，不是密码学批准证明或令牌权限缩减，不提供外部请求服务。没有环境变量/磁盘配置/登录读取入口，没有开启实网的 CLI。
- 关闭门在凭据回调、DNS 和连接之前执行；代码只提供未来可注入的内存凭据回调。本轮测试只用未解析的 AUTH_SLOT 符号，或回调返回 None，未取得任何真实或伪造的有效令牌值。已授权将来也只在该任务内保留一次内存引用，stop 后释放引用，不宣称 Python 字符串可被安全擦除。
- 使用现有 PinnedHTTPSConnection、默认验证证书的 SSL 上下文和原主机名 SNI；每次目标解析结果必须全部公开、非组播，连接固定到已核验 IP。HTTP/用户信息/危险端口/伪域名/输入中的鉴权参数拒绝；不使用环境代理、Cookie 或 Authorization 头，关闭底层调试输出。
- 控制/分片响应不跟重定向。直链最多 3 次跳转，每跳 HTTPS/域名检查；从未加令牌的原始 URL 解析相对跳转，后续 auth=false。带 access_token 等参数的 Location 拒绝，不转发原鉴权或 Cookie。
- socket I/O 超时固定 30 秒；响应读取有 120 秒预算，并受授权有效期限制；JSON 最大 256 KiB，分片原始载荷最大 32 MiB、multipart 附加部分最多 4096 字节，线缆请求路径最大 16 KiB，回读单块最多 1 MiB、累计长度不得超过目标文件。
- 请求规范的 repr 不显示 URL/参数/正文；所有错误使用固定允许的原因码；重复 JSON 键、缺失/布尔 errno、错误内容编码、重复/冲突长度、异常正文均拒绝/脱敏。分片成功允许官方所示的仅 md5 响应，仍校验与本地分片一致。
- 只拥有一个活动请求；并行新请求拒绝且不丢失旧连接。stop 只 shutdown/close 本客户端连接、关闭其读取流，不操作系统中其他任务、不删除云端数据；清理错误不回显且不报告成功停止。

实际 OS DNS 解析以及标准库 HTTP 头部读取没有独立硬截止线程，30 秒 socket 超时不等于恶意慢速头场景下的绝对总时限；120 秒是响应读取检查预算。独立进程写入、真实网络停止延迟、服务器是否已处理请求均未验证，不能声称内核配额或硬实时取消。M2/M3 实网联合验收仍需验证这些边界，不能由假客户端 stop=True 代替。

## 请求与任务生命周期

probe 编码 uinfo(vip_version=v2) 与 quota；身份不符、未知会员、容量不完整/过期都停止，upload_permission 保持 unverified。文档上限是参考而非该账号权益探查成功；没有凭空增加“查单文件上限”的接口。实际应用上传权限仍须在获准后核实，接口错误不自动刷新授权或换凭据。

分片任务绑定同一 path/size/哈希序列/uploadid/节点；确认记录由适配器拥有，改变 session 身份字段或重复提交拒绝。按预上传返回的所需片号发送，未确认完不 create；原始 uploadid、响应正文与下载链接不落任务 JSON。M3 任务层补了可选 required_parts 接口，默认内存模拟器仍发送全部片；假 HTTP 联动测试只发送服务器声明缺少的片，最后用全文件回读校验，而非将略过片假称为新发送。

HTTP 绑定调用现有 AdapterContext/SpaceGuard 检查点，不新增整文件磁盘缓存；multipart 会产生有界内存拷贝，JSON/哈希列表也占内存，不宣称零内存开销。响应/协议参数有界不代表真实后端临时开销已确认，M2 仍要求声明并联合验收。现有模拟 API 拒绝 live transport；只有假 HTTP 诊断对象以 simulation 模式参与，cloud_verified、delivery_eligible 永远为 false。

## 本轮验收矩阵

| 项目 | 已实现/通过 | 未测/未放行 |
| --- | --- | --- |
| REST 绑定 | 身份、容量、目录、precreate、locateupload、multipart、create、元数据及完整流式回读的假响应协议测试 | 无真实账号请求；权限与权益未知 |
| 禁止覆盖 | 公开策略 1/1 不覆盖语义及改名失败检查；严格 0 契约保持关闭 | 预上传 0 未获明确依据，真实严格冲突失败未证明 |
| 安全通道 | 默认授权门、TLS/SNI/公开 IP、允许域名/方法、重定向、固定超时、字节限额、错误脱敏及资源关闭测试 | 实际节点/重定向范围、DNS/头部硬时限和停止延迟未实测 |
| M2/M3 接线 | 假 HTTP 接入源闸门、所需片号、SpaceGuard 与全量回读；已有空间/异常测试继续运行 | 真网盘 5 GiB 全过程、后端实际开销、真实失败闸门仍需同一任务联合验收 |
| 结果 | 只保留模拟资格，实网资格始终 false | M4 分享、M5 整体恢复、M6 国内领取未完成 |

测试命令：`python3 -m unittest discover -s tests -p test_baidu_protocol.py -v`、完整 discover、compileall 和 git diff --check。本轮不重新跑已有 NCBI 模拟演示或历史基准；完整测试包含既有小夹具，新增 HTTP 联动夹具仅 4 MiB+2 字节，全部本地/内存，禁止真实 socket。证据见 `docs/validation/mvp-baidu-http-2026-11-08.json`。

## 真正下一步

绑定代码和无凭据测试已完成，不以用户先给令牌为工程前置。当前技术 pending 是严格冲突语义的依据/政策决定，而不是“没写绑定”。之后才可能申请一次性真实身份/权限探查与上传回读批准：既有已校验的 1,379,902 字节 NCBI FASTA，当前项目会话控制已有海外节点的隔离单任务进程，目标 `/apps/Xtransfer/mvp-validation/20261108-ncbi-ecoli-01/`；仅现有 access_token 临时内存使用、不刷新/不读 Cookie/密钥、不建持久授权，结束停止进程并移除新增凭据副本，保留原授权、源和云端对象。不分享、不发消息、不部署。令牌仍有现有应用权限，程序路径约束不缩减它，任何冲突实验或替代改名政策须明确加入批准范围。当前状态 pending、未尝试，未调用真实接口。

[ability]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8A%E4%BC%A0/%E8%83%BD%E5%8A%9B%E8%AF%B4%E6%98%8E/
[precreate]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8A%E4%BC%A0/%E9%A2%84%E4%B8%8A%E4%BC%A0/
[create]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8A%E4%BC%A0/%E5%88%9B%E5%BB%BA%E6%96%87%E4%BB%B6/
[part]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8A%E4%BC%A0/%E5%88%86%E7%89%87%E4%B8%8A%E4%BC%A0/
[host]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8A%E4%BC%A0/%E8%8E%B7%E5%8F%96%E4%B8%8A%E4%BC%A0%E5%9F%9F%E5%90%8D/
[mkdir]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E5%88%9B%E5%BB%BA%E6%96%87%E4%BB%B6%E5%A4%B9/
[uinfo]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E8%8E%B7%E5%8F%96%E7%94%A8%E6%88%B7%E4%BF%A1%E6%81%AF/%E8%8E%B7%E5%8F%96%E7%94%A8%E6%88%B7%E4%BF%A1%E6%81%AF/
[quota]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E8%8E%B7%E5%8F%96%E7%BD%91%E7%9B%98%E5%AE%B9%E9%87%8F%E4%BF%A1%E6%81%AF/
[metas]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E8%8E%B7%E5%8F%96%E6%96%87%E4%BB%B6%E4%BF%A1%E6%81%AF/%E6%9F%A5%E8%AF%A2%E6%96%87%E4%BB%B6%E4%BF%A1%E6%81%AF/
[download]: https://pan.baidu.com/union/doc/%E5%9F%BA%E7%A1%80%E7%BD%91%E7%9B%98%E6%9C%8D%E5%8A%A1/%E4%B8%8B%E8%BD%BD/
