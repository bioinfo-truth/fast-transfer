# 合并结果未知的只读核查

`fast_transfer.task_upload --inspect-commit-proof`只用于**唯一未知操作为commit**的任务。它不重发写请求，不用“未找到对象”推断原请求失败，不清理云端对象。目录/预上传/分片未知仍停止待人工处理；当前没有这些阶段的通用接续入口。

## 输入与范围

先查看任务状态并核对原账号和任务设置摘要。操作人员以只读客户端核查新任务精确目标，准备本人私有目录内的0600 JSON定位文件，字段仅为：

- `job_id`与`task_spec_sha256`：原任务及已审核设置摘要。
- `path`：原任务精确目标路径，不是另一个文件或重命名副本。
- `fs_id`：操作人员查到的对象ID（整数）。
- `bytes`：原审核文件大小（整数）。

定位文件不是成功证明。程序必须独立核对实时账号、原目录身份、对象路径/fsid/大小，并完整流式回读MD5/SHA256，与独立重读的原本地源摘要一致。仍需原源文件；源丢失不能借此绕过校验。

使用与[上传说明](mvp-task-upload.md)相同的账号/对象范围、原地OAuth文件、helper/guard参数，增加：

```sh
python3 -m fast_transfer.task_upload --tasks-dir /PRIVATE/TASKS JOB_ID \
  --approve-job JOB_ID --approved-task-sha256 REVIEWED_TASK_SHA256 \
  --authorization /PRIVATE/authorization.json \
  --expected-account-sha256 EXPECTED_ACCOUNT_SHA256 \
  --sdk-helper /PRIVATE/ft-sdk-codec --sdk-helper-sha256 HELPER_SHA256 \
  --sdk-guard /PRIVATE/baidu-sdk-codec-guard.py --sdk-guard-sha256 GUARD_SHA256 \
  --inspect-commit-proof /PRIVATE/object-locator.json --timeout 600
```

执行前须明确该账号/精确对象的只读核查与完整回读范围；不是允许扫描全盘或重放写请求。真实HTTP在核查模式拒绝非GET请求，先于认证读取；协议不安装写入钩子或写许可。没有凭据搜索、刷新或跨机移动。

## 结果和恢复

成功仅在适配器停止确认后保存commit确认与完整核验收据，阶段变为`cloud_verified`；合成后端仍为`test_cloud_verified`、`cloud_verified=false`。输出不含定位信息/会话/链接。后续上传执行器看到确认的commit不会再次提交，交接及清理可以继续。

目录或对象不匹配、回读损坏/失败、源变化、账号不符、超时、停止未确认：保留未知意图和源文件。可修正定位或排除网络问题后再次只读核查，不重新上传、不删任务换job。若确认保存后、核验状态保存前崩溃，原上传执行器只会重新核查/回读，不重复提交；这是保留确认与核验两步的恢复窗口。

该功能不能证明服务器上的未知分片/预上传状态，也不处理快速完成类型；对象没有找到时仍未知。操作人员可以暂停处理或拒绝该任务，保留记录待核查，不能以此宣称所有异常都能自动续传。

## 证据

7项新增及相关回归共106项禁网测试通过，实际SDK编码器配合合成服务器，覆盖响应丢失但对象已合并、只读完整核验后接续、对象/摘要/账号范围拒绝、错误回读保留未知、停止未确认、源变化、HTTP非GET在认证前拒绝及其他未知类型不接管。未进行新真实账号核查或VPS部署，不替代上传强杀与资源验收。
