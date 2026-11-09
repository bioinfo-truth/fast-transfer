# 严格候选响应适配层与拒绝测试

`contract.go` 是可复用的 Go wire/schema 验证层，按固定 UK、对象 listing 和分享响应字段实现具体拒绝规则；不是仅列建议，也没有改原生产客户端的默认拒绝门。**未接入网络/凭据 provider，未证明服务器支持这些契约。** 原 UK/ShareSet 宽容解析仍在原库中，未来必须通过受审入口明确替换使用，不能声称原函数已自动修好。

## 已实现

- JSON 最大 64 KiB、深度 16、数组 128、节点 2048、字符串 8192；所有层级重复键、额外 JSON、缺失/非整数/非零 errno 均拒绝。不接受浮点或字符串身份及非正/越界 UK、FSID、shareid。
- ParseIdentity 核对预期 owner 的 `cookie_netdisk_uk` 命名空间、1–128 位 ASCII opaque session/task 与最多五分钟范围；输出不可经 JSON 构造内部字段的候选 Principal。ParseObject 核对同一范围指纹/期限，防止换任务、会话、大小或延长期限复用。**Principal 只表示调用者提供的字节形状/范围一致，不是服务器认证证据**；真实来源与新鲜度必须来自未来允许且受审的 transport，不能把重新喂旧响应当新验证。
- 精确对象匹配 path/fs_id/size/isdir/md5，拒绝缺失、重复 ID/路径、错配或未绑定 Principal。路径必须在明确 Xtransfer 前缀，拒绝控制字符、点段、非规范形式。这里只验证候选 listing 的内容，不证明请求真的限定了父目录或对象内容未被覆盖；HTTP 请求范围/owner 来源/原始摘要语义仍需实证。
- ParseShare 必须有正 shareid、显式成功码和规范 HTTPS 百度分享 URL；拒绝用户信息、端口、fragment、编码路径、异常 query、非法短码。返回类型不把请求密码填回；默认 fmt 各种格式及 JSON 不输出内部工作链接。不是内存擦除或反射攻击保护。
- `FixtureLedger` 仅接受 `fixture-` 任务，无 transport、凭据或磁盘写入。Begin 在任何未来发送之前消耗唯一意图并进入 creation_unknown_fixture，固定七天及四位小写字母/数字提取码；参数错误不产生意图。超时/坏响应不会使其回到可重试状态。响应只到 created_unverified_fixture；share/owner/session/fsid/path/期限任一映射冲突进入不可恢复 quarantine。Stop 后不可重放。
- Mapping 是未来适配器的映射证据输入，不是假设存在的官方 JSON 接口。`verified_fixture` 也只表示离线契约一致，LiveEligible 始终 false；LiveConnect 始终返回 live_entrypoint_closed。内存意图不跨进程持久，不能作为真实进程重启后的幂等性保证。

## 已执行验证

同一已核验 Go 1.27.3，标准库依赖，无新增模块：gofmt、编译、`go vet contract.go contract_test.go` 通过；专用 strict-adapter.test 在初始化前启用原级别 Landlock/seccomp、空环境/独立新 HOME 后，**15 项测试运行通过**。包括前轮原解析器接受的缺成功码/非正身份/非法链接现在拒绝，账号/命名空间/会话/时间、精确对象、范围防重绑、JSON 预算/歧义、提取码/期限、私密结果格式化、unknown/映射冲突/停止重放和真实系统调用边界探针。

最初十二项通过后，审查发现候选 Principal 还需绑定完整范围与期限，已补上指纹和到期校验，并增加三个针对性测试后重编译/运行最终十五项。没有重跑旧 helper/requester/config/Python 套件冒充进展；原生产补丁未改动。当前文件独立通过 vet，不表示上游包既有 PrepareBDStoken 诊断已修复。

复现：只编译 `contract.go` 与 `contract_test.go`，使用隔离 wrapper。`restricted_adapter_exec.py` 复制到专用隔离根目录后只允许该目录的 strict-adapter.test；执行前创建新的空目录，拒绝复用已有路径，保留外部假文件/符号链接与 socket 探针。程序以 fixture 数据运行，没有任何真实百度请求、真实秘密或工作链接。证据见 `docs/validation/pcs-strict-adapter-2026-11-09.json` 和 `.txt`。

## 此范围完成后的具体阻碍

本层解析/范围/单意图拒绝测试已完成。继续获得真实能力证据需要当前仍不可用的三项输入，而不是更多模型或真实凭据试错：

1. **访问渠道依据**：现有站点拒绝仍有效；需原访问控制/工具对具体拟议账户动作和端点范围可验证的允许依据，不能自行换 CLI/代理/OAuth 推定绕过。
2. **可信服务/对象契约**：Cookie UK 的当前服务支持、与预期账号的独立绑定、已上传 Xtransfer 样例的访问范围及 shareid→owner/精确 fsid 集合/有效期的映射能力都未核实。不能给 Mapping 伪造“真实服务证明”或以路径前后查验冒充原子绑定。
3. **真实阶段许可**：只有前两项明确后，才可审阅原 dr-who-server 指定构建的一次 ≤5 分钟身份/指定对象只读范围（凭据类别、来源/用途、必要请求与无持久化/清理），再单独审阅该精确样例一次七天受控建链及映射核验/unknown/取消范围。此处不申请、不接收秘密，也不实施这些动作。

真实接入还需把本层嵌入受审编排器、可信证据来源、持久防重和受控返回通道；这些必须围绕已确认服务契约实现，不能先开放 live 再补证。详细阶段范围和已排除的“同账号就跨应用可用、Cookie/OAuth互换、CLI打印即交付、原 parser 接受即可信”路线见 `docs/pcs-identity-share-plan.md`。
