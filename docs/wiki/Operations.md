# 人工录单试运行操作手册

> 2026-11-11最新：用户已将同一Goal恢复active；较早blocked叙述是历史状态。成本/工时和跨地区测速后置。新增错误分类与恢复建议通过224项禁网回归，尚未部署；不能将历史VPS运行包等同本地新代码。本轮只做本地工程，远端发布待后续允许联网时同步。操作入口见[Operations](https://github.com/bioinfo-truth/fast-transfer/wiki/Operations)。

适用：本人当前单账号、单worker、公开HTTPS数据、固定版本官方SDK/API上传、境内原生分享。当前实测包括902,395字节蛋白和834,262,758字节基因组＋7,187字节报告，两个任务均收到本人下载成功反馈；具体限制以已审核Task设置为准，不承诺任意规模或固定跨境速度。本手册不启动收费/淘宝/网站，也不依赖项目号解析。

## 1. 录单与审核

每单在私有队列登记：订单引用、收到时间、官方数据记录/版本、文件范围与格式、manifest位置/摘要、总字节、Task ID、状态、实际阶段耗时、人工介入说明、交付收据摘要和保留约定。客户身份/联系方式与公开仓库分开保管。预计完成时间可填“待测”；报价未约定则保持空白，不用历史单文件速度作SLO。不要把这些业务字段塞入严格白名单manifest。

操作人员从官方记录审核公开性、版本、大小、源站摘要和获取/交付依据，形成[manifest](https://github.com/bioinfo-truth/fast-transfer/wiki/MVP-Scope-and-Input)。只给项目号时人工选定文件，解析插件不是前置。intake的accepted仅表示输入通过；缺依据转manual_review，受控访问/禁止分发/带凭据URL拒绝。

## 2. 固定运行版本与串行队列

VPS使用[已核对的独立运行包](https://github.com/bioinfo-truth/fast-transfer/wiki/Product-and-Architecture)，保留旧版。下面值全是占位符，应填本人已核验的路径/摘要；认证参数是文件位置，不能把令牌值放进命令。目录本人所有、0700，私有JSON 0600。当前验证Linux运行环境提供`flock`。

```sh
umask 077
ft_release=/PRIVATE/RELEASE
ft_tasks=/PRIVATE/TASKS
ft_manifest=/PRIVATE/reviewed-manifest.json
ft_auth=/PRIVATE/authorization.json
ft_account=REVIEWED_ACCOUNT_SHA256
ft_helper_sha=VERIFIED_HELPER_SHA256
ft_guard_sha=VERIFIED_GUARD_SHA256
ft_run() {
  /usr/bin/python3 -I -S -B "$ft_release/launcher.py" "$@"
}
ft_work() {
  flock -n "$ft_tasks/.serial-worker.lock" /usr/bin/python3 -I -S -B "$ft_release/launcher.py" "$@"
}
```

统一使用ft_work运行源/上传/清理，锁忙就留在人工队列，不另起worker。Task内部锁只覆盖同一任务，不是跨任务资源预留；手工绕开串行锁不属于本试运行方式。show遇task_busy表示原进程持锁，应查原进程，不删锁或换任务。

## 3. 建立不可变任务、下载和核验

```sh
ft_run intake "$ft_manifest"
ft_run task --tasks-dir "$ft_tasks" create "$ft_manifest" --max-file-bytes 1073741824 --part-bytes 4194304
```

默认单文件上限1GiB、4MiB片（最多1024片），不是先下载后决定；超限转审核。改用8/16/32MiB需账号级别允许，代码执行前重新核查；更大单文件设置须重新审核磁盘、内存及实际账号限制，不修改既有Task快照。manifest最大100文件、1MiB JSON，仍逐文件串行。

将create输出的job_id/task_spec_sha256登记到私有队列，后续始终使用同一个任务：

```sh
ft_job=ACTUAL_JOB_ID
ft_spec=ACTUAL_TASK_SPEC_SHA256
ft_run task --tasks-dir "$ft_tasks" show "$ft_job"
ft_work task --tasks-dir "$ft_tasks" download-next "$ft_job" --timeout 1800
```

source_verified才进入上传。下载检查实际大小、源站已给摘要并独立计算MD5/SHA256；运行期保留5GiB底线及提前停止余量。实际低空间准入、源进程中断恢复见[故障证据](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)。不完整源从头重启，不承诺Range续传。

## 4. 上传、完整回读与普通暂停

```sh
ft_work task_upload --tasks-dir "$ft_tasks" "$ft_job" \
  --approve-job "$ft_job" --approved-task-sha256 "$ft_spec" \
  --authorization "$ft_auth" --expected-account-sha256 "$ft_account" \
  --sdk-helper "$ft_release/bin/ft-sdk-codec" --sdk-helper-sha256 "$ft_helper_sha" \
  --sdk-guard "$ft_release/scripts/baidu-sdk-codec-guard.py" --sdk-guard-sha256 "$ft_guard_sha" \
  --timeout 900
```

cloud_verified才是此文件真实核验完成，test_cloud_verified不得交付；delivered此时仍false。回读使用任务剩余预算，任务最多900秒，socket空闲30秒；控制/写请求最多120秒。资源周期采样不是精确峰值或净带宽。

普通暂停向核对过PID/启动时间/所属任务的**Python worker**发送一次SIGUSR1，等待status=paused、stop_confirmed=true及进程终态。它等待当前请求和确认落盘，可能不立即退出。SIGINT/TERM/KILL、超时及网络中断仍可能留下unknown；观察超时不等于进程已停止，不能因此启动另一worker。

## 5. 按状态恢复

| 状态/原因 | 操作 |
| --- | --- |
| 源downloading/source_failed且文件完整 | `ft_work task --tasks-dir "$ft_tasks" recover-source "$ft_job" --index INDEX`；独立重哈希，成功不重下 |
| 源不完整、无远端意图 | 保留需调查的片段证据后，显式`restart-incomplete-source`同上参数，再download-next；不删Task/未知文件 |
| 预上传/部分片已确认，unknown=0 | 用同一上传命令续传；跳过确认目录/预上传/分片 |
| 合并确认、回读失败 | 原上传参数追加`--readback-only`；合并回执须存在，模式强制拒绝写请求；没有回执则在凭据前拒绝 |
| 唯一unknown=commit | 不重复合并；准备0600精确对象定位文件，使用原参数追加`--inspect-commit-proof /PRIVATE/locator.json`，核对身份/大小并完整双摘要回读，见[说明](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan) |
| 唯一unknown=非最终part | 普通续传仍拒绝。明确允许相同会话/序号/字节有限重传时，原参数追加`--retry-unknown-part-once PART`；一次尝试先落日志，原unknown快照保留，失败不循环；不适用于最终片、合并或分享 |
| 目录/预上传未知、多个未知、快速完成分支未支持 | 保留状态转人工，不清空意图或新建替代Task绕过 |
| http_timeout / http_deadline / http_io_failure | 先等worker终态，检查unknown和确认回执；有unknown走对应核查入口，不能仅凭超时重发；已确认合并仅回读恢复 |
| http_rate_limited（HTTP429） | 停止本轮，人工等待服务恢复；不自动循环或无限等待Retry-After。重开仍按原Task收据/unknown选择入口 |
| http_auth_rejected（HTTP401） / http_access_denied（HTTP403） | 停止本轮，检查指定授权或访问权限；403不等于令牌过期，不自动刷新或换账号 |
| uinfo/账号/凭据错误 | 停止写入，查安全诊断和指定认证文件，不索密码或自动刷新/换账号；有效令牌须在原位置按已有流程恢复 |
| 空间/内存/配额拒绝、source_changed | 暂停接单/执行，核对实际资源或源身份；不降低校验、改源摘要或重放成功操作 |
| 原生分享超时/结果不明 | 保留分享意图/输出，先核查分享记录；不再次share set |

精确定位JSON仅含job_id、task_spec_sha256、path、fs_id（整数）、bytes（整数），必须指向原任务精确对象；没有找到对象不能推断合并未执行。

重试参数三者互斥：readback-only、inspect-commit-proof、retry-unknown-part-once。不存在“所有错误自动循环重试”。每次失败记录时间、固定原因码、是否有未知意图、原进程是否终态及人工决策。

## 6. 逐文件空间复用与最小交接

一个文件真实cloud_verified且无未知后，可显式清理**该文件本地载荷**：

```sh
ft_work task_cleanup --tasks-dir "$ft_tasks" "$ft_job" --index INDEX
```

清理重新核对源身份和双摘要，先保存删除意图，只删除精确文件并同步目录；状态cleaned，保留Task/源/上传/核验/交付收据和云端对象。恢复或调查中的证据不自动清理；本轮鼠任务源仍保留。已确认清理后再download-next处理下一文件，避免预取挤满硬盘。

全部文件真实cloud_verified或cleaned才能导出：

```sh
ft_run task_handoff --tasks-dir "$ft_tasks" "$ft_job" --output /PRIVATE/new-handoff.json
```

导出文件必须不存在。仅经私有渠道传交接JSON及其SHA256到国内，不传认证文件或uploadid。国内在已审核仓库运行delivery check，校验发送方可信摘要和账号，再按清单逐文件用既有原生登录执行meta，核对path/fs_id/大小。MD5必须如实记录：v1要求与内容摘要一致；v2的native_md5与handoff完整回读内容摘要分开，见[私有交付](https://github.com/bioinfo-truth/fast-transfer/wiki/Operations)，不得把差异写成匹配。

## 7. 一次分享、本人领取与回填

核对所有文件后，对这个任务目录只运行一次`BaiduPCS-Go share set --period=1 EXACT_NEW_TASK_DIRECTORY`，省略自选密码，客户端随机生成4位码。命令意图和原始结果保存在本人的私有目录；链接/提取码不进入公开仓库。share失败与传输分开恢复，不重传已确认文件。

国内将实际meta/share结果填为新的0600 observation JSON；初始recipient=pending。使用真实handoff摘要/账号保存新收据：

```sh
python3 -B -m fast_transfer.delivery --handoff /PRIVATE/handoff.json \
  --handoff-sha256 TRUSTED_HANDOFF_SHA256 --account-sha256 REVIEWED_ACCOUNT_SHA256 \
  record --observation /PRIVATE/observation-pending.json --output /PRIVATE/delivery-pending.json
```

v2观察文件字段：schema=`fast-transfer-human-observation-v2`，job_id/task_spec_sha256与handoff一致，integrity=`handoff-full-readback`；metadata按清单顺序每项只有index/path/fs_id/bytes/native_md5（实际原生摘要32位小写hex），身份/大小必须匹配。share只有url/code/created_at/expires_at，时间为Unix整数秒；recipient只有status/logged_out/downloaded/confirmed_at，pending/failed时间为null，confirmed需真实领取反馈、logged_out和downloaded为true、确认时间在分享有效窗口。未知/多余字段拒绝。原生摘要无法识别时先核查，不改填源摘要。

将收据及其工具返回SHA256私下回填VPS，关联原Task：

```sh
ft_run task_delivery --tasks-dir "$ft_tasks" "$ft_job" \
  --receipt /PRIVATE/delivery-pending.json --receipt-sha256 TRUSTED_RECEIPT_SHA256
```

本人在未登录窗口实际领取并下载后，依据明确反馈追加observation-confirmed及新delivery-confirmed，recipient.confirmed_at填实际确认时间；重复上述record/attach步骤，保留原pending。只有这时Task delivered=true。收据依据是本人反馈，不声称独立浏览器位置或领取文件哈希已由程序验证。未反馈保持pending，下载失败记failed，不代填成功。

## 8. 保留、关单与试运行边界

- 分享当前1天；过期不等于云端对象删除。重新建链先核对记录并由操作者明确决定，不自动重复。
- 已核验本地载荷可按第6步释放；原样例、恢复调查证据和全部收据默认保留，不由清理命令递归删除。
- 云端当前不自动删除。队列记录实际保留约定和复核日期；没有约定就不承诺永久保存/商业SLA。配额不足拒绝新任务，云端删除须另行针对精确对象决定。
- 关单核对manifest范围、每文件大小/内容摘要、一次分享结果、本人领取反馈、pending/confirmed历史及资源/人工介入记录；测试/模拟成功不能冒充交付。
- 单worker、单文件默认1GiB、每Task最多100文件是已有入口边界；多用户并发、无限流式传输、自动续期、客户身份认证、支付和计费不在本阶段。

真实记录：[蛋白任务](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)、[鼠多文件任务](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)、[源/令牌/空间故障](https://github.com/bioinfo-truth/fast-transfer/wiki/Validation-Plan)。当前服务速度、配额和平台权限以具体账号与实测为准，人工队列不自动向客户报时或发消息。

## 2026-11-11：离线稳定性补充

运行中低空间已通过合成故障注入验证停止与跳过确认片恢复，不是实际ENOSPC验收。空间不足可能阻止新reason写入；以已有持久意图/收据为准，不承诺磁盘耗尽后仍能落日志。新增错误分类与测试尚未部署VPS；既有真实样例不重跑。详见仓库 `docs/workflow-stability.md`。

## 2026-11-11：状态诊断与重复操作审计

`task show` 新增 `recovery`：仅基于同一锁内的本地状态给建议，`advisory_only=true`、`automatic_action=false`，不读认证、不执行恢复、不输出私有收据/分享/会话。建议不是授权或服务端证明；执行入口仍独立核验原Task、摘要、账号和已授权范围。阶段状态及delivered原有含义不变。

| recovery.action | 对应入口和限制 |
| --- | --- |
| download_next | 原Task的 `task ... download-next JOB`；仍须通过来源、空间和原有执行授权，不能据建议新增真实传输 |
| recover_source | `task ... recover-source JOB --index INDEX`，本地独立校验；若不完整，保留调查片段后显式 `restart-incomplete-source`，不承诺Range续传 |
| resume_upload | 原参数 `task_upload`，跳过确认目录/预上传/分片；不等于重新建任务 |
| readback_only | 原上传参数加 `--readback-only`，必须有合并确认回执且拒绝写请求 |
| inspect_commit_proof | 唯一未知commit，原参数加 `--inspect-commit-proof` 和精确定位文件；不重复合并 |
| review_one_time_part_retry | 仅提示人工审议：唯一未知非最终片且尚无尝试记录；明确允许后才能使用 `--retry-unknown-part-once`，失败耗用次数不重置 |
| manual_review | 目录/预上传未知、多个未知、最终片未知、已耗用有限重试或人工阶段；不自动改错误码/清unknown |
| synthetic_only | 合成记录不能交付或晋升真实核验 |
| export_or_check_handoff | 所有文件阶段为真实核验/清理且绑定官方后端；使用 `task_handoff --output` 的原有入口核查/导出，导出器仍独立检查全部核验收据。任务不存导出事件，因此不能推断已交接、已分享 |
| await_recipient / review_recipient_failure | 已关联pending/failed观察，等待领取或人工调查；不自动重新分享。经私有 `delivery record` 追加观察，再用 `task_delivery --receipt --receipt-sha256` 关联原任务 |
| delivery_recorded | 已有关联confirmed本人领取收据；不重复分享、上传或要求同一文件再领取 |

未知写入优先于错误类别：即使reason变成限流、认证拒绝、超时或空值，未知commit仍只建议核查，不被清零。一次非最终片重试失败后保留原unknown及尝试，重开诊断转人工。show在合成测试中保持SQLite字节摘要不变，使用既有排他锁，无新迁移或持久表。

审计复用既有实际exec/SIGKILL/重新exec、unknown commit GET-only核查、有限重试耗用、交接拒绝未核验及pending/confirmed防回退测试；不重复实现上传/交付逻辑。新增通用合成测试入口 `tests/test_task_recovery.py`，领取confirmed/pending诊断也接入原有收据测试。无实网、部署或新交付。本轮仅本地工程，Wiki本地镜像同步，远端发布待后续允许网络时进行。

## 2026-11-11：SQLite容量耗尽边界

在独立临时数据库通过 `max_page_count` 实际触发SQLITE_FULL，不填满真实磁盘。新增一个测试分别覆盖part/commit两个子场景：合成服务已接收写入，finish_operation保存回执之前，测试包装器的容量探测INSERT实际失败。原持久unknown保留、没有伪造确认/完整核验/交付，适配器停止；重新打开原Task在factory之前拒绝，不再次发片或合并。

7项相关禁网测试通过，使用实际本地SDK编码器与合成服务。不是实际收据UPDATE触发SQLITE_FULL，也不是文件系统ENOSPC/日志回滚或生产磁盘耗尽验收；不保证此时还能持久化新reason。只增强数据库容量失败的恢复证据，不扩大此前真实操作范围。仓库证据为 `docs/validation/sqlite-capacity-fault-2026-11-11.json`。
