# M2/M3 资源不足、取消与慢响应停止边界

2026-11-09，本轮只运行微小合成数据、fake 连接/流及隔离子进程。新增 20 项测试；干净预期提交副本中的必要回归 **122 项通过，零失败、零跳过**，历史未提交四项未拷贝/运行。真实网络、账户、下载站、上传/分享和本地网络服务均未访问/启动，M2/M3 真实全过程验收仍未完成。

## 实现与可保证的范围

- `upload_stage.TransferControl` 提供进程内 `cancel()` 和可选绝对 monotonic deadline。在源读取、各传输阶段及分片/回读的协作检查点判断，固定原因为 `transfer_cancelled` / `transfer_deadline`；AdapterContext 的 checkpoint/临时写前检查也接入。不是 CLI/JSON 或跨进程取消接口，没有将 workflow 的人工 cancel 改成抢占器；真实样例入口未增设授权或新的连接路径。
- 调用返回后先检查控制/空间；当检查点已经观察到取消，就不继续下一分片、提交、metadata 或回读验证；提交已经发生则保留，不删除、不重试或声称回滚。最后 stop 中发生取消也撤销验证/模拟交付资格。原真实资格默认关闭、16 MiB 模拟上限、5 GiB + margin 保留线均不变。
- HTTP 客户端追踪 exchange、读取及 stop 清理的在途状态。慢 request/getresponse 返回后检查停止/预算，读取晚到的数据在关闭后拒绝；停止状态被检查到后拒绝回复。并发开始拒绝；底层 exchange/read 或另一个 stop 清理仍在途时返回 false，而不是仅凭 connection.close 报已停止。关闭异常不报告成功停止；stop 本身仍可能阻塞。
- `stop_confirmed=true` 只说明本地适配器按契约已停止；结果仍须通过内容、停止、状态落盘等门。`verification_complete=true` 单独仅说明曾完成内容核验；stop=false/异常时整体仍 manual_review、资格 false，不能当作成功或真实交付。任意第三方后端谎报 stop=True 的情形不在信任模型内。

检查点、取消事件和最终完成判定不是跨线程原子事务：检查点之后仍有调度竞态，最后控制检查之后的最终状态落盘/return 窗口未实现取消与完成的原子裁决。HTTP stop 追踪底层 I/O/关闭，不保证调用方消费者已退出或其队列已清空；真实编排须等待 worker 退出并核对最终记录，不能只凭一次 stop=True 发放交付资格。

没有新线程抢占执行器、硬磁盘配额或通用 supervisor。取消在调用阻塞时仅设置事件，finally stop 只有主调用展开时才能运行。DNS、工厂、源文件读取、状态 fsync、任意 transport/close 仍可能阻塞；本次不为其承诺硬时限。HTTP 原 IO_TIMEOUT=30 秒是单次 socket 操作超时，不是 DNS/整任务硬截止；REQUEST_BUDGET=120 秒在检查点判断，不能抢占不返回的实现，也不能保证 120 秒内终止。测试将该预算临时设为 10 毫秒，并证实停顿期间仍不能返回，释放后才报 deadline。

## 新增验收矩阵

| 窗口 | 实际测量/执行 | 结果与边界 |
| --- | --- | --- |
| 分片调用停顿后取消，配合 checkpoint | 独立子进程中真实线程等待 Event；取消后观察约 30 ms，再释放 | 观察时仍阻塞；释放后接受 0 字节，不提交 |
| 分片调用忽略取消 | 相同真实停顿，返回前写本轮测试文件 4 字节 | 取消后确有一次晚写；下一检查点拒绝后续阶段。不是远端写入上界证明 |
| 回读停顿时取消 | 独立子进程线程停顿，释放后检查 | 无完成验证/交付资格 |
| 分片调用永不返回 / stop 永不返回 | 子进程内 daemon 线程保持等待，不释放 | 无结果可用、不能宣称停止；同 job 再启动为 duplicate_job。只随本轮测试子进程退出结束，不是生产 supervisor |
| 提交前取消 | 最后一个分片返回时取消 | 接受 16 字节，但未调用 commit |
| 提交后取消 | fake commit 完成后取消 | 保留合成对象，不进入 metadata，不回滚或重发 |
| 回读中取消 / stop 中取消 | 真实函数检查点 | 不输出成功或模拟交付资格；stop 中取消撤销 verification_complete |
| 低空间，分片停顿中或一片之后 | 动态 Probe 返回 reserve+margin−1；未填满磁盘/降低保留线 | 配合 checkpoint 的停顿分片接受 0；一片后情况接受 4，不接受下一片；可能无法保存最终记录，保持 state_persisted=false |
| stop 返回 false / 抛异常 | 合成 stop 失败 | 内容可能已验证，但状态 manual_review、stop_confirmed=false，资格 false，异常原文不回显 |
| 启动前取消 / deadline 已过 | 控制检查在任务启动前 | 零后端动作/载荷，不创建任务来假装已执行 |
| HTTP request / headers / read 停顿时 stop | fake 连接的真实线程等待，shutdown/close 故意不释放 | 首次 stop=false、线程仍在；手动释放后固定停止原因、不返回晚到数据，最终 stop=true |
| HTTP cooperative close | fake shutdown/close 释放 Event | 读取/头部线程退出，未返回成功数据；记录调用耗时，不推导真实 TCP/TLS 行为 |
| HTTP close 自身停顿，第二次 stop | 第一次 stop 在线程中等待，主线程第二次 stop | 第二次 false，避免把尚未完成的关闭写成停止成功 |
| HTTP 头部校验中 stop | fake getheaders 同步触发 stop | 当时 stop=false；exchange 拒绝并释放 reply，之后 stop=true |
| HTTP deadline 在停顿中到期 | 10 ms 合成预算，等待超过该预算后释放 | 超期不能强行唤醒，释放后报 http_deadline，不进入 headers |

上述 20 个 unittest 方法包含 23 个合成场景。每个场景在单独 Popen 子进程中执行；事件/线程是真实调度，HTTP 连接、远端对象、空间下降和超时行为为合成，不是公网实测。记录每次停止调用、释放到返回时间、接受载荷/实际晚写、返回后观察窗内写入和请求读取长度。最终日志/机器证据见 [JSON](validation/m2-m3-stop-boundaries-2026-11-09.json)及[原始合成输出](validation/m2-m3-stop-boundaries-2026-11-09.txt)。

## 字节、时间与未知结果

所有新源文件仅 16 字节，分片/回读请求上限 4 字节，HTTP fake 读取要求也核对为 4。合成 MemoryCloud 在返回结果后约 30 ms 观察内新增写入为 0；这不证明任意外部适配器没有后台写者。忽略取消的分片示范实际向测试文件晚写了 4 字节；生产中的晚写量依赖具体后端，不能将此数字推广。

通用流程仍限定单片≤32 MiB、回读请求块≤1 MiB；这些是每次调用/请求的载荷约束，**不是整进程 RSS 或所有副本上界**。协议 multipart 及内存模拟器可能同时持有副本；不能把“逐片”写成零缓存。低空间检查是协作的，不会自动监测或中断正在阻塞的调用；检查点之间其他进程仍可占用磁盘。

本次释放人为停顿到上传线程返回约 0.6–2.2 ms，HTTP fake stop 调用也记录了实测时间；这些包含具体机器调度/代码路径，不是 SLO、硬停止时限或真实网盘性能。JSON 保留精确值，不用固定阈值测试性能，避免把一次调度结果变成保证。

同步调用或 stop 永不返回时，正常结果文件也可能无法生成；缺结果必须保持未知并人工检查，不能由超时推断无远端副作用。M5 的先存意图/重复任务拒绝继续适用，不用新 job_id 绕过未知结果。当前上传目录独占也拒绝同一 job 的再次调用；不能据此推导跨任务、跨主机或远端 exactly-once。

## 隔离、复现与后续

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_stop_boundaries test_baidu_protocol test_upload_stage test_space test_workflow test_workflow_process test_approved_sample test_isolated_candidate
```

沿用已审查的 runner：libseccomp 拒绝 socket/连接等系统调用并继承到全部测试子进程，worker 实际验证 socket=EPERM；显式空 HOME/配置和最小环境、`-I -S -B`、DEVNULL stdin、关闭额外 FD。没有文件系统沙箱；文件范围靠审查后的代码和本轮 TemporaryDirectory 约束，不声称隐藏宿主文件。仅终止本轮自己创建的子进程，超时会 kill 该测试子进程；不动其他进程/旧资料。fake resolver 只返回字面地址给 fake factory，不执行 DNS 或连线；没有凭据加载或新依赖。未启用内核保护的普通测试发现会跳过新增测试；正式日志无跳过。

首次 61 项运行发现本轮接线误将 control 传给不接受它的 SpaceGuard，造成 25 failures / 1 error；已修复并加强 stop 测试避免前置失败造成假通过。后续 61、63、120 项逐步通过；最后补齐竞态/低空间场景和时间测量定义后，干净副本 **122 项通过**。没有用旧结果替代最终代码验证。

下一步的最小工程方案（候选，未实现）：若产品需要确定的任务取消响应时间，增加独立子进程监管与外部持久意图；超期时停止本地 worker 并标未知、保留对象/记录，再人工核查。仍不能用杀进程证明远端未提交，也不能自动重试。真实 M2/M3 联调需具体允许范围和可信后端证据；M4 登录/分享仍关闭，本轮没有改变 Browser Use site safety gate 的既有约束。
