# 通用流程稳定性执行与验收

## 2026-11-11：已获授权并完成稳定性运行包安装检查

用户明确允许安装检查及同步GitHub/Wiki。同一Goal已由用户恢复active。a6c75a1697fff73ce40e0ca53dfeb22bdd41b6aa已安装至VPS独立版本目录，归档SHA256 `0bd3a5fbfcefb4a2b6e2c4a6682c6b52ea2b9962e5f4d0c52fd05ea2d48cc2aa`。52个成员/51个载荷的摘要、权限、所有权和Python语法核对通过；7个CLI帮助、readback-only选项、通用合成任务创建与show恢复建议及数据库不变检查均在继承性内核禁网、临时HOME下通过。

首次合成任务在临时文件系统因可用空间不足5GiB而拒绝；没有绕过底线或重装，确认已安装目录后，在空间充足的另一现有文件系统创建新的独立临时测试通过。未改原任务，保留旧版、不切换常驻服务、不读取网盘凭据、不下载真实源、不上传网盘或创建分享。部署代码归档不等于新数据传输验收。

仓库证据 `docs/validation/stability-runtime-deployment-2026-11-11.json`。其中remote_published=false是生成安装结果时的快照；本次随后按授权同步发布文档，不修改原始安装证据。实际ENOSPC/OOM、认证自然到期和长期运行仍未验收；自动刷新不是现有能力。较早“待允许部署/发布”是当时状态，已被本条明确授权和安装结果更新；此前受阻来源/操作的限制不变。

## 当前状态入口（2026-11-11，Goal已由用户恢复active）

以[当前人工录单验收总表](current-readiness.md)区分本地代码、历史真实证据和未部署边界。最新完整禁网回归224项通过，恢复诊断/收据再核对15项通过；此前130/210项等数字是历史快照。成本/人工工时及跨地区测速按用户决定后置，不能继续当作当前前置。最新错误分类与恢复建议尚未部署，旧VPS版本不证明新代码已上线。本轮仅本地工程，远端文档/Issues/PR未同步；历史记录保留原文。


2026-11-11。沿用既有 Goal，不另建目标；执行范围按用户确认调整为下表。当前 Goal 控件读取仍为 blocked，现有工具不能修改正文或恢复 active；本文记录执行范围，不代表控件已更新。成本/工时统计、跨地区测速、跨服务重启续传后置。此前受阻的来源/操作不恢复，不引入外部模型、真实认证、上传或分享。

| 优先级 | 要求 | 当前证据与剩余边界 |
| --- | --- | --- |
| P0 | 运行中空间下降安全停止 | 合成任务在已确认第一个分片后降低可用空间，第二片/合并均未发送，重开 Task 后跳过确认片。不是实际 ENOSPC；完全无空间时不能保证新错误记录落盘，既有持久意图/收据为恢复依据 |
| P0 | 超时/限流/认证异常明确停止 | HTTP 429/401/403分别给出限流/认证拒绝/访问拒绝；socket超时独立归类。不自动重试、刷新或推断平台errno。合成探测拒绝仅一次请求并持久原因；真实令牌自然到期与刷新未测 |
| P0 | 重启不重放成功或未知操作 | 复用既有进程中断、未知commit核查、非最终分片一次重试测试；新增分片已产生效果但超时的合成测试，重开时factory前拒绝，不合并、不重发 |
| P1 | 各阶段独立恢复与领取状态 | 复用 Task 源恢复、上传续跑、GET-only回读、私有交接和交付收据。新增回读429后只GET恢复，合并始终一次；合成验证不标真实核验/交付。未领取不标完成由既有delivery测试覆盖 |
| P1 | 审计与手册 | 安全错误码不记录响应正文/异常私密文本；手册给出各错误的恢复入口。合成与真实证据分开，发布版本不等于VPS已部署 |

测试入口为 `tests/test_stability.py`，使用通用sample.bin和example.org占位信息、实际本地SDK编码器与合成HTTP响应。通过隔离运行器执行，内核禁止网络并由子进程继承；没有真实账号请求或新交付动作。证据见[离线验收记录](validation/workflow-stability-2026-11-11.json)。

操作规则：先确认旧worker终态并独占同一任务；按原Task的持久收据决定恢复入口。网络错误与写入结果未知是不同维度；即便错误码为限流/认证，也不据此清空已经落下的未知写意图。HTTP403仅表示访问拒绝，不断言令牌过期。

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

本轮完整禁网回归224项通过；内部方法命名调整后15项诊断/收据测试再次通过。日志摘要与边界见[状态恢复审计证据](validation/task-recovery-audit-2026-11-11.json)。

## 2026-11-11：SQLite容量耗尽边界

在独立临时数据库通过 `max_page_count` 实际触发SQLITE_FULL，不填满真实磁盘。新增一个测试分别覆盖part/commit两个子场景：合成服务已接收写入，finish_operation保存回执之前，测试包装器的容量探测INSERT实际失败。原持久unknown保留、没有伪造确认/完整核验/交付，适配器停止；重新打开原Task在factory之前拒绝，不再次发片或合并。

7项相关禁网测试通过，使用实际本地SDK编码器与合成服务。不是实际收据UPDATE触发SQLITE_FULL，也不是文件系统ENOSPC/日志回滚或生产磁盘耗尽验收；不保证此时还能持久化新reason。只增强数据库容量失败的恢复证据，不扩大此前真实操作范围。仓库证据为 `docs/validation/sqlite-capacity-fault-2026-11-11.json`。

## 2026-11-11：获准的真实隔离文件系统耗尽测试

用户明确允许后，在VPS私有挂载命名空间内创建固定32MiB tmpfs（0700、nodev/nosuid/noexec），继承性内核禁网。合成文件写入实际触发ENOSPC；已提交unknown记录的最小SQLite表更新实际触发SQLITE_FULL。释放填充文件并重开后integrity_check=ok，记录仍unknown，canary不变；进程退出0。

随后独立核对测试挂载0、测试临时目录0，并按精确SHA256核对后移除远端测试脚本。未读网盘凭据、改原任务、下载真实源、上传或分享，也未切换服务。脚本保留在仓库 `tests/support/isolated_enospc.py`，应只按独立明确范围在私有挂载命名空间中运行；不随普通单元测试执行。

本次补足真实文件系统错误与SQLite恢复的边界证据，**不是完整Task worker的ENOSPC验收**，不外推任意硬件故障、OOM或日志写入中途强杀的持久性。此前SQLITE_FULL page cap测试和合成Task错误仍分别保留；不将三种证据混称同一真实流程。机器记录为 `docs/validation/isolated-enospc-2026-11-11.json`。
