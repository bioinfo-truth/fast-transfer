# M6 实际领取验收准备与本地回执契约

本轮只准备清单、机器可读契约和本地只读核验工具。没有指定实际中国境内设备/测试人，没有真实分享/领取批准，没有新传输。海外上传回读、合成文件匹配或人工声明都不能代替中国境内实际领取；M6 实测 pending、未尝试，不能标 MVP 已完成。

## 工具与三种记录

`python3 -m fast_transfer.acceptance` 不联网、不读取账号、不开分享链接、不调用下载器、不修改 M3 写入门、不更新 workflow 的交付状态。已有 M1–M5 及 OpenList/直接 API 基线保持不变。

| 记录 | 必须绑定的内容 | 信任边界 |
| --- | --- | --- |
| receipt_expectation | 同一 job_id、原 manifest SHA-256、文件映射 SHA-256、源版本指纹、文件名/精确字节/MD5/SHA-256；source/upload_readback/share 前序记录指纹及时间/结果，分享到期时间 | prepare 仅从 simulated_cloud_verified/share_draft 阶段的模拟 workflow 生成，origin 永远 simulation；外部手填可标 unverified_operator_record，但不是事实证明 |
| receipt_observation | 同一 expectation/映射/任务与唯一 attempt_id；设备匿名指纹、地点声明/证据指纹、实际领取方式/开始结束时间/结果、观察指标 | 仅接收 simulation 或 operator_claim；地点、自填时间、引用指纹不证明地点或授权；不接受 kind=real 升级 |
| local_receipt / receipt_audit | 此次本地文件计算的字节/完整 MD5/SHA-256、hash 起止与耗时、原观察记录、复核原因；audit 检查记录间一致性和重复 attempt | check 当次只证明已选本地文件；audit 只审查传入记录、不重读文件、不验证指纹所引用内容，也不证明回执来源可信 |

所有输出真实资格 cloud_verified/share_verified/location_verified/delivery_eligible/delivered 均 false。加载包含 true 的回执会拒绝；填写完整 operator_claim 仍有真实前序、地点及授权未核验原因。不存在网络授权入口或自动 delivered 状态转换。JSON、摘要和本机时钟不构成签名、地理位置证明或防篡改账本。

## 本地命令（未执行真实领取）

```sh
# 仅从已有离线任务生成期望，要求双哈希已具备；不会读取源载荷。
python3 -m fast_transfer.acceptance prepare --jobs-dir /tmp/ft-jobs --job-id job-workflow --output expected.json
# 在将来明确选定的接收端，对已经存在的本地文件只读核验；本轮仅测试合成小样例。
python3 -m fast_transfer.acceptance check expected.json observation.json fixture.fna --output receipt.json
# receipts.json 是回执数组；检查结构、同一任务映射、重复 attempt 和时间等。
python3 -m fast_transfer.acceptance audit expected.json receipts.json
```

示例 `examples/m6/expectation.synthetic.json` 对应合成的 `b'ACGT' * 128`，精确 512 字节；`observation.template.json` 绑定该示例指纹，地点/指标/时间默认未知。它们不是 NCBI 实测数据，前序记录缺失是有意保留。实际使用应由正确任务生成 expectation，不复用示例的任务和指纹；更改 expectation 后必须重新绑定 observation 的 spec_sha256。

check 要求所选文件基名一致、普通单硬链接文件、最终路径不是符号链接，精确长度匹配；本地单文件上限 1 TiB（本工具限额，不是网盘权益），读取至预期长度、最多 1 MiB 内存块，完整算双哈希并复核 inode/长度/mtime/ctime 与当前路径，变化则停止。只读原文件，不复制载荷，不改名/覆盖/删除。读取者自身及其文件系统不受信任时，这些检查不能构成远程证明；父目录必须由操作人员正确选择。

`--output` 只独占创建新的 0600 小记录，不覆盖；目标盘仍要求 5 GiB + 256 MiB + 64 KiB 余量。输入/输出记录至多 64 KiB，audit 每批最多 32 条且仍受字节上限限制。无 output 时只输出 JSON，不修改数据或工作流状态。无大文件基准、下载缓存或复杂调度。重复 attempt 仅在传入审查批次检查，没有跨设备全局台账；再次生成回执不意味着允许重新传输。

返回码 0 仅表示本地匹配或结构审查完成，**不是 M6/MVP 通过**；缺长度/摘要、错任务/映射/文件名、重复尝试、非法字段、伪造真实资格会失败；相同长度但摘要不符输出 manual_review/返回码 2。前序缺失、领取未知、时间错误或地点未核验会留在 review_reasons，即使文件确实匹配也不交付。

## 时间、指标和人工操作的区别

前序 source → upload_readback → share → acquisition.started_at → acquisition.finished_at → 本地 hash_started_at 按 UTC Unix 秒检查顺序；缺项保持缺失，不填造。时钟偏差应人工解释或重新提供证据，工具不自动调整。领取开始晚于声明分享期限会提示复核；这不是平台断言“过期必然删除文件/中断既有下载”。本地核验允许在实际领取完成后再做。

hash_elapsed_ms 是本次本地读盘算摘要的单调时钟耗时，不是下载时长。observations.elapsed_ms、network_received_bytes、minimum_free_bytes、manual_steps 由接收方观察填写，未知填 null；字节计数可能包含其他流量/协议开销，不用文件大小反推账单或速度。reported_space_below_reserve 只提示声明低于 5 GiB，不表示程序实际监控了整个下载的空间。receipt_observation 中 acquisition.kind 与 method 明确模拟/人工方式，后续真实数据也只作为待人工核验声明。

指纹用于绑定外部保管的非公开证据，工具不解引用。不要将真实姓名、私有路径、IP、客户信息、分享原链接、提取码、Cookie 或令牌放入契约或公开库；额外字段拒绝，错误固定原因码。设备/地点的支持证据及原始日志应在另行批准的私密渠道保留和返回，公开只放经审查的脱敏汇总。

## 将来实际验收操作清单（全部 pending）

1. 明确同一任务和公开生物文件版本、来源/分发依据、精确字节、源站摘要与本地完整双哈希；不得把生成数据当生物样例。准备 M2 原始证据及 M3 实际上传对象身份/路径、长度、完整回读双哈希和停止结果，标清各自实际时段与指纹。
2. 完成明确范围内的 M4 真实受控建链，绑定该精确对象、接收范围和期限；人工验证对象/内容/权限，私下保管链接及提取码。人工声明或格式通过不替代内容核验。
3. 由明确的中国境内设备/测试人，在批准的方法和时间窗口内实际领取同一文件；记录匿名设备标识及可复核的境内位置依据。自填 mainland_cn、IP 地理数据库或海外主机回读不能单独证明此步。当前不替用户挑设备或联系测试人。
4. 接收方记录领取起止、方式、结果、实际观察到的耗时/流量/最低空闲空间及人工操作；未知项保留未知，失败/结果不明不自动重传或新建分享。独立 attempt_id 只识别尝试，不授予再次传输权限。
5. 在该端对已领取的本地文件完整核对长度和双哈希，生成新回执并通过批准的私密方式返回；保留原文件/日志，禁止自动清理。人工串联 M1–M5 真实证据、接收端及观察证据，解释不确定项。只有完成真实证据复核，才能另行确认业务验收；本工具永不自动认定 delivered。

## 后续所需最小用户输入与许可（清单，不是本轮申请）

- 境内接收设备及实际测试人/操作者；匿名标签与可接受的位置/操作者证据方式。保管真实身份信息的私密位置。
- 精确任务/文件/网盘对象、允许接收范围、分享期限与链接/提取码的私密交付方式；范围应明确测试对象及意外/未知对象保留，不覆盖旧资料。
- 实际领取方法与允许的时间/流量/存储条件；是否允许失败后的另一次尝试，未明确则停止。
- 回执/日志返回渠道和人工核验人；不包含凭据或私人路径的公开汇总范围。

缺口是这些实际接收端、M3/M4 真实证据和明确范围尚未具备；不是本地准备被拒绝，也不要求重复申请 M3 授权。本轮已完成其余独立准备。

## 本轮验证

新增 8 项离线聚合测试使用 512 字节合成文件，禁用 socket。覆盖绑定错误、字节及两种摘要独立不符、前序缺项/未知、时间倒序/过期、重复 attempt、模拟/JSON true 冒充真实、秘密字段、符号链接、记录不覆盖和契约示例。工作区应为 127 项、干净提交应为 123 项（四项历史未提交测试保留），最终结果见本轮证据 JSON。没有读取真实账号、下载数据、创建/访问分享、发消息或改变部署。
