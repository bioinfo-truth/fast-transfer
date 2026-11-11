# 通用任务的 SDK/API 上传与恢复

2026-11-11。`fast_transfer.task_upload`已接通通用Task、固定版本官方Go SDK请求编码、受控HTTP、持久上传会话与完整流式回读。当前完成禁网合成响应验证，未部署到VPS或对新对象执行真实账号操作。不是完整交付MVP。

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
- 任一写入结果未知：在调用认证提供器之前停止，输出`task_unknown_operation_requires_inspection`。**当前没有通用只读核查/人工裁决命令，不能直接重运行、改数据库或删除意图来绕过。** 保留任务及源文件，后续需完成核查恢复入口。
- 预上传返回快速完成类型目前保守停止待核查，尚未实现该分支的通用接管。源下载仍不支持HTTP Range字节级续传。
- 使用既有磁盘预算、元数据增长上限和SDK内存准入估算；这些不是VPS峰值RSS、吞吐或断电验收。核验后自动清理、私有交接导出、国内分享与交付记录尚待接线。

## 验证依据

34项Task/上传针对性测试及相关回归总计211项通过，全部在继承性seccomp禁网环境中运行，使用真实SDK编码器和合成服务响应。覆盖会话/分片/合并恢复、未知操作防重、账号/任务范围绑定、完整hash列表、源变更、配额不足、回读损坏和停止未确认。通用上传重启主要为重开持久任务测试；已有源阶段SIGKILL测试不等同于新上传执行器的强杀验收。后者和VPS真实验收仍待完成。证据见`docs/validation/task-upload-2026-11-11.json`。
