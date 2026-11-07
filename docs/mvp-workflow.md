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
