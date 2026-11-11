# 国内清单校验与私有人工交付记录

`fast_transfer.delivery`只做离线校验和保存记录，不运行原生客户端、不建立分享、不重传文件。原生meta和share操作仍由本人分别触发。新代码未经真实不同任务验收，不改变历史原样例。

## 先校验交接

将明确允许的私有清单交接到国内机器，本人私有目录0700、文件0600。使用发送方提供且经可信渠道核对的导出SHA256与预期账号摘要：

```sh
python3 -m fast_transfer.delivery --handoff /PRIVATE/handoff.json \
  --handoff-sha256 EXPECTED_FILE_SHA256 --account-sha256 EXPECTED_ACCOUNT_SHA256 check
```

新版交接为`fast-transfer-handoff-v2`：包含已审核manifest及其摘要（公开来源URL、版本、校验出处、分发依据/署名说明），校验来源与已核验对象的名称/大小/摘要。检查清单整体摘要、任务/账号、严格字段白名单、文件索引、唯一fsid/path及目标/摘要格式。成功只表示交接文件匹配，不查询账号、不证明云端对象当前仍在。SHA256是完整性绑定，不是发送者签名。不可把任意来源清单的自报摘要当作可信凭证。

## 原生操作及人工观察

在本人既有原生登录环境，对清单中的所有文件逐一运行meta，核对fsid/path/大小/MD5。再对该新任务目录创建一次1天随机码分享；若请求超时，先人工核查分享记录，不能直接重建。禁止复用历史原样例路径/链接。退出码不能单独作为成功证据。

将实际结果写入新的私有0600 JSON，不通过命令参数传链接或提取码。观察文件固定字段如下（下列为结构说明，须填实际值）：

- `schema`：`fast-transfer-human-observation-v1`。
- `job_id`、`task_spec_sha256`：与已校验清单完全匹配。
- `metadata`：按清单顺序，每项只有`index`、`path`、`fs_id`、`bytes`、`md5`，填本人meta核对结果；所有文件必须匹配。
- `share`：只有`url`、`code`、`created_at`、`expires_at`；百度HTTPS分享短链、4位码、实际创建及过期Unix秒数。支持记录过往确认，不把过期记录当作当前可领取承诺。
- `recipient`：只有`status`、`logged_out`、`downloaded`、`confirmed_at`。状态为`pending`/`failed`时确认时间为null；`confirmed`要求本人确认未登录窗口提取且下载成功，并填有效期内的Unix确认时间。不能仅看到分享链接就选confirmed。

命令：

```sh
python3 -m fast_transfer.delivery --handoff /PRIVATE/handoff.json \
  --handoff-sha256 EXPECTED_FILE_SHA256 --account-sha256 EXPECTED_ACCOUNT_SHA256 \
  record --observation /PRIVATE/observation.json --output /PRIVATE/receipt-new.json
```

输出收据文件必须不存在，创建0600、同步文件和父目录。文件包含最小交接快照、人工观察、记录时间及清单摘要。终端只输出状态、收据摘要和人工证据标记，不输出链接/提取码/路径。`confirmed`标为`delivered=true`的含义是**操作人员声明领取成功**，明确不是程序独立验证。pending/failed保持false，后续复核后保存新观察及新收据，保留旧记录，不覆盖；此命令不会重新分享或上传。

## 当前边界及验证

领取状态保存在国内不可覆盖的私有收据中，不把该文件自动回传VPS；源Task仅在下面显式关联命令成功后更新领取状态。来源/版本/分发依据已通过v2交接的审核manifest保存在收据内；它保留原审核结论，程序不重新裁定分发资格。源Task关联命令见下文。文件系统保护用于同一操作人员的协作环境，不构成恶意同UID进程隔离。

7项新增测试及48项Task/上传/交接/清理回归共55项通过，全部禁网、使用合成记录和合成分享URL，覆盖清单摘要/账号/对象不匹配、额外字段、无真实领取的确认拒绝、失效时间、私有权限与不可覆盖。未运行真实原生客户端、浏览器或新账号操作；不是不同任务真实验收。


## 将领取结果关联回源任务

若确实需要在源任务查询交付状态，先明确私有收据（其中有链接/提取码）回传范围，经私有渠道移到原机器本人0700目录，不携带登录凭据。未获该范围时可只保留国内私有收据，不自动跨机。

```sh
python3 -m fast_transfer.task_delivery --tasks-dir /PRIVATE/TASKS JOB_ID \
  --receipt /PRIVATE/receipt-new.json --receipt-sha256 EXPECTED_RECEIPT_SHA256
python3 -m fast_transfer.task --tasks-dir /PRIVATE/TASKS show JOB_ID
```

关联命令离线重验收据摘要、白名单、人工观察、账号、任务设置/manifest、每个精确对象与源任务真实回读收据，并要求无未知远端操作。保存SQLite内的私有收据快照与关联时间，不修改上传阶段或发网络请求。重复同一收据幂等，不复制记录；不同收据追加保留历史，已有confirmed不能被后续pending/failed覆盖。`show`仅显示`delivered`和`delivery_evidence=operator-attestation`，不打印链接或码。这个状态是历史人工领取确认，不保证分享现在仍有效。

v1交接缺少出处信息，新的国内入口会明确拒绝；应在原任务重新导出v2到新文件并重新核对摘要，不手工补字段冒充已审核来源。原历史单样例私有记录不升级、不重放。

7项新增来源/关联测试及55项相关回归共62项禁网测试通过，含pending后confirmed、重复关联不新增记录、确认状态不可回退、任务/摘要/来源变动拒绝、缺乏真实本地核验或未知操作拒绝。所有账号/分享/源核验记录均为合成测试数据，未进行真实跨机收据传送或新任务领取验收。

## 原生元数据与内容摘要分开记录

`fast-transfer-human-observation-v1`继续要求原生metadata的MD5与期望内容MD5一致，不放宽既有记录。新增v2明确`integrity=handoff-full-readback`：路径/fs_id/大小必须逐项匹配已验证v2交接清单，`native_md5`保存实际原生元数据摘要；内容MD5/SHA256保留在handoff，依据已完成的官方API完整回读，不把两者混写成相同。

本次834MB实测原生MD5字段与独立源/完整回读MD5不同，具体平台表示/计算原因尚未确认；不能据此泛化所有网盘MD5的语义。没有绕过内容核验：两文件完整回读已通过，原生精确对象身份与大小再次匹配，差异原样保留。v2不允许仅凭metadata声明完整性，仍要求handoff为official-api-full-md5-sha256-readback；也不免除用户实际领取/下载确认。旧v1观察不会自动转换。
