# 通用任务的 SDK/API 上传与恢复

2026-11-11。`fast_transfer.task_upload`已接通通用Task、固定版本官方Go SDK请求编码、受控HTTP、持久上传会话与完整流式回读。通用运行版本已部署并完成新公开小文件真实上传/回读/交付；834MB任务部分执行后有未知分片，完整状态见[验收记录](mvp-acceptance-status.md)。不是完整交付MVP。

## 输入和命令

先按[任务入口](mvp-task-entry.md)创建审核后的manifest任务并完成一个文件的源下载，再通过`show`读取JOB_ID和`task_spec_sha256`。后者绑定任务、manifest及应用名/分片大小等设置；变更设置需要重新审核。SDK helper与禁网guard按[编码器说明](sdk-request-encoder.md)构建和检查，二者须提供实际SHA256，不能把示例占位值直接运行。

在明确该新对象的账号操作范围后运行：

```sh
python3 -m fast_transfer.task_upload --tasks-dir /PRIVATE/TASKS JOB_ID \
  --approve-job JOB_ID --approved-task-sha256 REVIEWED_TASK_SHA256 \
  --authorization /PRIVATE/authorization.json \
  --expected-account-sha256 EXPECTED_ACCOUNT_SHA256 \
  --sdk-helper /PRIVATE/ft-sdk-codec --sdk-helper-sha256 HELPER_SHA256 \
  --sdk-guard /PRIVATE/baidu-sdk-codec-guard.py --sdk-guard-sha256 GUARD_SHA256 \
  --timeout 600
```

授权文件只在原机器明确位置延迟读取access_token，不搜索、刷新或搬运凭据。一次处理一个已校验源文件，默认600秒、最多900秒；不是任意大小/无限时长服务。账号摘要、源摘要、目标、任务设置与后端类型必须匹配。公开输出仅含固定状态、文件索引、大小和安全错误；uploadid、fs_id、完整路径等留在私有任务数据库。

真实执行成功输出`status=cloud_verified`及`delivered=false`。合成后端只能输出`test_cloud_verified`、`cloud_verified=false`，其任务不能升级成真实账号任务。`cloud_backend_connected=true`仅表示绑定真实后端，不代表交付。

## 恢复规则和限制

- 每个目录/预上传/分片/合并请求前先保存unknown意图；确认后保存收据。任务锁覆盖整个执行过程。
- 预上传已确认但节点查询失败：已有会话持久化，重运行只重新查询上传节点，不重复预上传。
- 已确认分片跳过；服务端只要求部分分片时，合并仍使用完整原始hash列表。
- 已确认合并后回读失败：重运行只做对象核查和完整流式回读，不重新上传。回读长度、MD5、SHA256与源独立摘要全部匹配，且适配器停止确认后，才保存核验状态。
- 任一写入结果未知：在调用认证提供器之前停止，输出`task_unknown_operation_requires_inspection`。**唯一未知为commit时已有[只读核查入口](unknown-commit-inspection.md)**，操作人员提供精确对象定位后，须完整双摘要回读成功才确认。其他未知仍停止；不能改数据库或删意图绕过。
- 预上传返回快速完成类型目前保守停止待核查，尚未实现该分支的通用接管。源下载仍不支持HTTP Range字节级续传。
- 使用既有磁盘预算、元数据增长上限和SDK内存准入估算；这些不是VPS峰值RSS、吞吐或断电验收。核验后逐文件清理与私有交接导出已有独立命令，见[半自动交接说明](half-automatic-handoff.md)；国内原生分享由本人触发，人工领取私有收据及源Task关联已实现，见[私有交付说明](private-delivery.md)。

## 验证依据

34项Task/上传针对性测试及相关回归总计211项通过，全部在继承性seccomp禁网环境中运行，使用真实SDK编码器和合成服务响应。覆盖会话/分片/合并恢复、未知操作防重、账号/任务范围绑定、完整hash列表、源变更、配额不足、回读损坏和停止未确认。此为早期同进程重开任务证据；后续新增实际exec/SIGKILL/再次exec测试，见下文。VPS真实验收仍待完成。证据见`docs/validation/task-upload-2026-11-11.json`。


## 实际进程强杀与新进程恢复

新增`tests/test_task_upload_process.py`及独立worker。首次worker是实际Python exec进程，SDK同样启动实际禁网helper；服务响应为合成，状态另存临时JSON。每次合成请求后持久保存服务状态。父进程收到明确检查点标记、确认worker仍在运行后SIGKILL并wait回收，再启动新的exec worker，重新打开Task/SDK适配器及服务快照。

覆盖四个场景：

1. 预上传确认持久后：重启只重新定位节点，不重复目录/预上传。
2. 第一个4MiB分片确认后：重启跳过该片，只传剩余123字节，再合并。
3. 合并确认后、回读前：重启仅核查/回读，不重新传片或合并。
4. 合成远端已合并、响应交给协议前：杀进程后意图仍unknown；普通执行器拒绝继续，无新请求。新核查进程根据私有定位只读回读，确认后消除未知，原commit计数始终1。

前3场景使用4MiB+123字节两片载荷；第4使用小载荷。所有结果明确`test_cloud_verified`/`cloud_verified=false`。两项新增进程测试（含4场景）及相关回归共108项禁网测试通过，证据`docs/validation/task-upload-process-2026-11-11.json`。这证明本地SIGKILL/新进程恢复与合成服务持久状态下的防重；不是内核断电、真实百度持久语义、VPS峰值内存/速度或实际大文件故障验收。


通用CLI后续新增周期资源采样，成功/受控失败结果附`resource_samples`；准确边界与版本区别见[资源采样说明](runtime-resources.md)。它不替代空间/内存准入，也不是精确峰值或完整实网验收。


## 普通暂停与紧急中断

开发分支新增边界暂停：本版`task_upload` CLI在上传执行期间接收`SIGUSR1`，处理器仅设置内存标志，不在HTTP调用中抛异常。操作人员先核对目标worker的PID、启动时间与所属任务，再向该worker发送一次信号；等待它自己的终态结果，不能根据等待超时另起worker。不要向不支持此功能的旧版本发送该信号，默认信号行为可能直接终止进程。

收到请求后，已经开始的目录/预上传/分片/合并调用继续到成功回执落盘或原有失败退出；下一个写入意图建立前检查标志，正常暂停输出`status=paused`、`stop_confirmed=true`、`cloud_verified=false`，退出码0，保留源/会话/确认回执。暂停不是交付完成。再次运行同一任务仍执行完整范围/源/账号检查并跳过已确认操作。若合并已确认，则仅接续核查/回读。信号恰在最后核验阶段到达时，该文件可能正常完成核验；以最终状态为准。

`SIGUSR1`不取消在途请求、不绕过超时/预算限制。如果请求失败或回执无法落盘，原unknown仍保留，不输出安全暂停；已有unknown也仍在读取凭据前拒绝执行。`SIGINT`、`SIGTERM`、`SIGKILL`以及服务端响应丢失的紧急中断语义没有改变，仍可能产生unknown。当前未知48号片不会被该功能解除或重发。

本次仅完成本地禁网验证，未将新代码替换到VPS运行版本。真实exec测试在合成服务接收片0后、响应交还协议前等待信号；父进程确认该worker存活后发送真实SIGUSR1，子进程继续解析响应、持久回执后退出。随后新的exec沿用任务完成片1及合并，目录/预上传/片0均只发生一次。另覆盖暂停前无凭据读取、控制回执暂停、合并后仅回读、停止确认失败和在途失败保留unknown；不将合成响应等同百度服务端可靠性保证。

本轮26项上传/实际进程测试及94项相关回归共120项禁网测试通过，记录见`docs/validation/upload-pause-2026-11-11.json`。


后续暂停功能运行包2772a7a已独立安装VPS：51个归档文件、50个载荷的摘要/权限/所有权及Python语法核对通过；补齐引用的BaiduPCS-Go许可证。7个CLI帮助入口和SIGUSR1置位/原处理器恢复检查在内核禁网下通过。保留旧63a9840版本，未启动服务、读取凭据或执行上传；现存48号片未知不变。安装和离线信号检查不等于实网分片恢复，证据见`docs/validation/pause-runtime-deployment-2026-11-11.json`。
