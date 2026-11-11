# 通用任务入口：持久状态和源下载

2026-11-11。`fast_transfer.task`是人工录单MVP的通用任务层，不再绑定原单次NCBI样例。**本轮已接源下载；通用云端上传、交付和自动清理尚未接入，不是完整MVP。** 不读取认证配置，不把manifest或本地收据当作远端权限。

## 操作

在仓库工作目录运行。任务父目录须预先存在、本人所有、权限0700，不能是符号链接或缺失挂载点；使用自己选定的私有目录。

```sh
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS create /PRIVATE/manifest.json
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS show JOB_ID
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS download-next JOB_ID --timeout 1800
```

`create`接受现有已审核manifest契约，生成独立随机job ID并快照保存输入；输出中的JOB_ID用于后续命令。默认单文件上限1GiB、分片规划4MiB，最多1024片；可在create设置`--max-file-bytes`与`--part-bytes`，后者只允许4–32MiB。这里是本地任务规划，**不是实时百度账号/应用权限或上传准入**。

命令一次最多下载一个文件；前一个文件尚未完成上传阶段时不预取后续文件。真实源下载复用已有HTTPS/DNS/固定IP/TLS、长度/源摘要校验、独占创建及SpaceGuard实现。下载前和写入期间保留5GiB及256MiB提前停止余量；当前`source_admission=source-only`，不能据此宣称未来SDK内存/上传全过程预算已验收。下载结束再次独立计算MD5/SHA256和源文件stamp后保存收据，打印状态不输出URL、会话记录或凭据。

## 中断后恢复

```sh
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS recover-source JOB_ID --index 0
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS restart-incomplete-source JOB_ID --index 0
```

- 已完整落盘但未保存成功状态：recover-source只读重验实际文件大小和源摘要，成功后继续，无新网络下载。
- 只有部分文件或文件未创建：显式restart-incomplete-source才允许清理任务自有的不完整载荷并重置为pending。已经发出远端操作意图时拒绝；未知文件、链接/硬链接或完整长度文件保留待核查，不猜测删除。
- 源下载目前不支持HTTP Range字节级续传；不完整下载明确重启当前文件。不能将任务恢复写成源站断点续传已实现。
- 上次在新建空目录后、持久下载意图之前停止，空私有目录可复用；不能覆盖已有非空目录。

## 持久记录

每个任务目录0700，锁和SQLite数据库0600。使用`flock`限制同任务操作并发，SQLite FULL同步事务管理manifest快照、逐文件状态及远端操作意图，不另写一套JSON原子替换机制。SQLite仅保存本地记录，不是服务端成功/账号资格的证明；没有实测断电恢复，也不是多租户隔离系统。

内部`begin_operation`在外部调用前持久消耗directory/precreate/part/commit键，结果先记unknown。已消耗键不能再次启动；仍有未知操作时，不允许继续创建下一项。`finish_operation`仅接受匹配意图摘要、任务目标和严格白名单结构的私有收据，支持保存uploadid/分片信息；令牌/密码/Cookie不属于收据字段。它不发送请求、不授予运行权限，也不自动把任务标为cloud_verified或delivered。SDK薄适配器及可信运行范围需后续接入这些方法。

数据库原始值与会话收据只在私有目录内；公开`show`只给文件名、索引、大小、阶段、未知操作数量和明确的`cloud_backend_connected=false`、`delivered=false`。旧`workflow`保持模拟用途，不将其成功标志转换成真实交付。

## 已执行验证

18项新增禁网测试和96项相关回归，共114项通过。覆盖多文件快照、文件预算、真实download_verified+合成响应接线、空间不足不调用下载器、独占锁/权限/符号链接、部分文件显式重启、空目录窗口、完整源写入后SIGKILL/重开恢复、未知commit跨进程阻止重发、目标/意图收据匹配、1024分片收据容量、嵌套凭据字段拒绝以及CLI状态输出。真实子进程测试使用合成载荷，不连接源站或百度。

```sh
python3 -I -S -B tests/support/run_workflow_isolated.py \
  test_task test_intake test_safe_download test_space \
  test_workflow test_workflow_process test_upload_stage
```

该runner在执行前施加继承性seccomp禁网并使用独立临时HOME。命令行帮助也已在隔离Python导入路径中检查通过。未部署到VPS，未读取凭据或执行新远端写入。下一步为SDK薄适配器、真实上传/回读接线、逐文件清理及私有交付单，然后再做真实不同任务验收。
