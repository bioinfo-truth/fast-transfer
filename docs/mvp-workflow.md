# M4/M5 离线工作流与人工分享草稿

本轮实现 `python3 -m fast_transfer.workflow`，复用 manifest、源收据及 M3 模拟器/SpaceGuard。无真实模式、下载器入口、百度客户端、凭据加载、分享 API、链接探测、消息或交付发送。人工回填也是未验证声明，不能将模拟对象转换成真实分享资格。

## 官方公开依据与未知项

2026-11-08 只读核查[百度网盘官方帮助中心](https://pan.baidu.com/netdisk/help)：可为分享设置密码及有效期，到期失效；分享可能因平台规则被取消。未登录、未访问真实分享链接。该说明不证明当前个人开发者应用可创建分享，不证明具体账号资格、API 权限、期限档位或链接可用；这些均未知。没有把企业版能力或第三方教程推广到个人应用。

本轮没有新增未经核实的分享 API，采用人工操作清单/回填。未来真实分享还需要 M3 真实证据、明确的对象/接收范围和实际批准；此实现不满足也不申请这些许可。

## 单任务状态与持久化

| 状态 | 含义与后续 |
| --- | --- |
| source_pending | M1 已接受单文件输入；尚未核验本地源，只允许一次模拟入口 |
| simulation_running | 已持久保存开始意图；进程中断、记录失败时停在这里，不能自动重跑 |
| simulated_cloud_verified | 当前进程完成 M3 模拟、源/回读双哈希、长度、空间检查及确认停止；仅可回填模拟分享草稿 |
| share_draft | 人工填写了形式合格且文件映射相符的声明；不是已分享、已验证链接或已交付 |
| manual_review | 源失败、后端异常或人工检查；记录脱敏原因及待办，不自动恢复到可写状态 |
| cancelled | 取消后续本地流程；运行中的同步任务持锁，不能用此命令抢占；不取消远端请求、不撤销分享、不删除任何文件 |

任务目录以独占 mkdir 创建，权限 0700；本地非阻塞 flock 串行化同一任务，状态通过 0600 文件、fsync 和原子替换保存，每个状态至多 64 KiB。重复 job_id 不覆盖；旧任务失败后不得自动换 job_id 绕过未知结果。人工操作只登记 verify_source / inspect_commit_outcome / verify_share / cancel，不执行网络、不将状态重置为 runnable。确认旧结果后的新任务需操作人员显式安排；跨阶段断点恢复、多进程全局配额、分布式锁和完整重试调度尚未实现。

持久化前单独检查任务盘保留 5 GiB + 256 MiB + 两份状态上界；M3 继续使用已有同盘/分盘预算和检查点。没有内核硬配额；真实独立进程全过程空间保护仍待联合验收。任务盘不可写、空闲不足、残留 state.new、锁占用、符号链接/硬链接输入、超大/重复键/未知字段状态会拒绝。私有本机操作者可改动状态文件，校验不构成签名或可信账本。

加载任何 JSON 中的 true 都不能获得网络权限或真实交付资格。mode 只允许 simulation，真实资格字段读取时强制 false，未知字段拒绝。后端始终由代码新建 MemoryCloud，不从 JSON 选择客户端。已有 M3 的隔离不覆盖候选与真实写关闭门保持原样；此最小编排不重新实现 M3 或改变 OpenList + rclone 基线。

## 本地使用（示例命令，本轮未访问源站或账号）

先准备已有的本地文件及 `.receipts/0.json`，以及独立存在的私有 jobs/backend 目录。`create` 不下载；`simulate` 核对原 manifest 指纹及文件映射，M3 重读源并核验收据，源缺失或哈希不符则停。输入可含多个文件，但本版一次仅选择一个 index，不自动处理整批。

```sh
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow create manifest.json
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow simulate manifest.json --source-dir /tmp/ft-source --backend-dir /tmp/ft-backend
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow show
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow record-share synthetic-form.json
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow manual inspect_commit_outcome
```

`show` 输出交付清单草稿：文件名、长度、源摘要和模拟完整回读摘要、模拟目标路径、来源/校验/权利依据 URL、原 manifest/版本指纹、分享有效期及授权声明指纹、人工操作与核验状态。原 manifest 保留完整版本/权利说明；状态不复制自由文本、客户信息或本地绝对路径。JSON 输出不意味着账号/权利实际已核实。M6 实际领取、收据/双哈希比对和发送证据仍缺失，delivered 始终 false。

## 人工回填边界

模板为 `examples/workflow/share-form.template.json`。从 show 复制 mapping_sha256，明确填写未来 expires_at（UTC Unix 秒），保持 scope=simulation-only；模板的 0 会被拒绝。30 天上限是本地演练政策，不是百度期限档位。authorization_ref 是非敏感操作声明引用，存储时仅保留 SHA-256，不构成许可证明。

link 只做 HTTPS 主机/路径格式检查，接受 pan.baidu.com/s/… 或保留测试域 share.invalid/s/…，不会打开链接；禁止参数、片段、提取码和附加字段。只保存链接 SHA-256，不保存原链接、密码或令牌，也不输出它们。真实链接/提取码未来应在另行批准的私密交付环节处理；当前不发送给任何人。演练示例只使用 share.invalid。

人工操作清单：先获得真实 M3 核验证据与范围批准 → 在官方客户端选择精确对象 → 明确分享期限/密码 → 私下保管链接/提取码 → 逐项核对对象与授权范围 → 由指定境内测试人领取并核对字节/双哈希。此清单不代表这些步骤已被执行。

回填仅允许一次；错 job_id/映射摘要、越界 scope、已过期或超政策期限、链接格式不支持均拒绝。回填成功仍标 manual_claim_unverified；到期时 show 标 expired，不会重新建链或延长有效期。服务器实际取消、错文件链接、密码错误等无法通过格式识别；必须保持未验证，不得自动交付。

## 此轮验收与未完成范围

| 项目 | 此轮结果 | 尚缺 |
| --- | --- | --- |
| M4 人工回填与清单 | 合成成功/过期/错映射/越界/秘密字段拒绝，记录不含链接或密码 | 真实账号资格、真实对象建链、链接内容/权限验证、实际发送 |
| M5 单任务离线编排 | M1 接入、已有 M2 收据/源复核、M3 模拟、M4 草稿，持久状态、查看、锁、失败与人工待办 | 真实适配器接线、完整恢复/调度、真实状态可信证据及 M6 |
| 防重复/未知结果 | 重复启动/回填拒绝；先存意图，中断/未知结果不重试写入 | 远端不确定结果的人工实际核查 |
| 隔离与空间 | JSON true 不授予权限，资格恒 false；原空间保护保留 | 真实全过程空间和停止边界 |

新增 8 项离线聚合测试，合成载荷仅 1 KiB，禁用 socket；没有重新下载 NCBI 文件或跑旧性能基准。工作区 119 项通过，干净提交应为 115 项（四项历史未提交测试保留在工作区）。证据见 `docs/validation/mvp-workflow-2026-11-08.json`。M4/M5 仅本地独立部分完成，不能标整体验收通过。

## M5 进程中断与持久化窗口验收（2026-11-09）

本次复用现有 Job/flock/先存意图/原子替换，没有新增工作流或分享账本，也没有改动写入流程、5 GiB 保留线或默认关闭的真实后端。增加只读 `diagnose`：在原锁内检查残留 `state.new`（只 lstat，不跟随或读其内容）、加载并验证状态，返回固定原因码、可选 phase 和人工检查建议；不输出 mapping、状态自由文本或异常，不删除、修复、重置、重试或调用后端。可读记录也保持 `automatic_retry_allowed=false`，这只是诊断建议，不改变 `source_pending` 原有一次入口。

```sh
python3 -m fast_transfer.workflow --jobs-dir /tmp/ft-jobs --job-id job-workflow diagnose
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_workflow_process test_workflow test_space test_upload_stage
```

`diagnose` 成功返回结构化诊断时退出 0，包括需人工处理的状态；自动化必须检查 reason/status，不能用退出 0 当作任务成功。固定原因包括 `workflow_pending_state_file`、`workflow_incomplete_or_unknown_outcome`、`workflow_busy`、`workflow_state_missing`、`workflow_state_unreadable_or_invalid`、`workflow_record_readable`；其他访问错误归一为 `workflow_local_input_or_io_failure`。复用现有锁需要已有有效 lock、私有可写任务目录；目录不可用时只给出归一原因，不创建锁或修复目录。`show` 保留原清单语义，不是恢复诊断。

| 新增测试窗口 | 实际执行方式 | 结果 |
| --- | --- | --- |
| 意图写入前 | save 边界暂停，真实 SIGKILL，另起进程 | 旧状态不变、后端零次；第一次后续调用可执行，第二次被拒绝 |
| state.new flush 后、文件 fsync 前 | fsync 边界暂停并 SIGKILL | 保留 state.new 与旧状态，再启动不调用后端 |
| replace 后、目录 fsync 前 | replace 返回后暂停并 SIGKILL | 重开读到 running；后端零次，不重放 |
| 意图完成文件/目录 fsync 后、后端前 | save 返回后暂停并 SIGKILL | 重开 running，后端零次，不重放 |
| 后端调用中及竞争启动 | 合成后端记一次调用并暂停；第二进程竞争；再 SIGKILL | 竞争 busy，重开仍不重复调用 |
| 后端返回后、终态保存前 | 终态 save 前暂停并 SIGKILL | 后端一次，重开为未完成/未知，不冒充成功 |
| 意图文件 fsync 失败 | Python 注入 ENOSPC；不是填满真实磁盘 | 旧状态不变、保留残留、后端零次 |
| 意图 replace 失败 | Python 注入 EIO | 保留残留、后端零次 |
| 意图目录 fsync 失败 | Python 注入 EIO | replace 已可见，但后端零次，重开 running 拒绝重放 |
| 后端返回后终态文件 fsync 失败 | Python 注入 ENOSPC | 后端一次，保留 running 及残留，不重复 |
| 独立持锁者与启动者 | 两个真实子进程；仅杀测试持锁者 | busy；退出后内核释放锁，可诊断并执行首次入口 |
| 损坏/部分/缺失状态 | 测试目录构造不完整 JSON、错类型、缺字段及缺文件 | 固定诊断、无敏感合成哨兵回显、后端零次 |
| 残留为符号链接 | 链接到本轮合成哨兵 | 不跟随、不覆盖哨兵、后端零次 |

每个新子进程使用 `-I -S -B`、显式空 HOME/配置目录和最小环境、DEVNULL stdin、关闭额外 FD。runner 先加载子进程继承的 libseccomp socket 系统调用拒绝；worker 在导入工作流之前实际验证 socket=EPERM 及 HOME 为空。只读取仓库固定 fixture 和本轮临时输入，后端替换为本地调用计数器/未知返回值。普通 unittest 发现但未启用内核保护时，新进程测试会跳过；正式验收日志中 13 项均执行、无跳过。runner 自身及原工作流回归也受内核禁网；没有文件系统沙箱，文件范围由审查后的代码约束，不声称隐藏本机全部文件或提供完整恶意代码隔离。

本次新测试 **13 项**，原工作流回归 8 项；独立的预期提交代码副本（仅原已跟踪文件加本轮文件）中，连同受影响 space/upload_stage 回归共 **65 项通过**，退出 0。历史未提交四项未拷贝、未运行，也没有报作本次通过数。首次 18 项运行有一项 harness 未归一 JSONDecodeError，修正测试 worker 并增加窗口后 21 项通过；最终干净必要回归为 65 项，不改写初次失败。最终输出与代码哈希见 [JSON 证据](validation/m5-process-recovery-2026-11-09.json)及[测试日志](validation/m5-process-recovery-2026-11-09.txt)。

局限：真实的是本地进程 SIGKILL/重开和 flock，不是断电、内核崩溃或存储故障实测；fsync/replace 错误仅 Python 故障注入。未对真实后端、远端未知结果、磁盘控制器持久性或跨任务/主机并发作保证，计数器不证明远端 exactly-once。锁依赖同一未被替换的 inode，不能防私有目录拥有者恶意改状态/换锁；诊断也不认证状态。意图前未发生后端调用的任务仍可能首次执行，不能概括为所有重开一律不可执行。没有自动清理残留或恢复调度；人工检查之后也没有 reset-runnable 命令。**M5 仅本地验收范围补齐，真实 MVP 整体仍未通过。** 最小下一步是按诊断人工核对未完成记录；真实端到端阶段继续等待其各自可信接线、允许通道和交付验收条件，本轮不解除 M4 限制。
