# BaiduPCS-Go v4.0.2：默认拒绝的安全补丁候选

基线 `qjfoidnh/BaiduPCS-Go` tag v4.0.2，commit `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`。这是对实际固定源码的补丁，不是另一个 Python 登录模型。尚未编译、部署或验证真实能力，不能直接作为可安全登录的发行版。

`security-candidate.patch` 使用零上下文 diff，必须对 `baseline.json` 中逐文件 SHA-256 完全匹配的源码应用，并显式使用 `--unidiff-zero`。不能对未知版本宽松套用。补丁同时添加六项 Go 内存 transport 测试；它们本轮未运行。

## 实际变更与调用链

| 路径/函数 | 补丁行为 |
| --- | --- |
| requester.NewHTTPClient / lazyInit | 构造时初始化受保护 transport；真实 http.Transport 恢复标准证书/主机名校验，最低 TLS 1.2；CheckRedirect 全部拒绝。构造只设置对象，不发请求。 |
| requester.SetHTTPSecure / dialTLSFunc | 原来强制跳过校验的开关和备用 TLS 路径均改为严格校验，不提供关闭验证的兜底。 |
| guardedTransport.RoundTrip | 在任何底层传输前拒绝 HTTP、非允许域后缀、userinfo/fragment/异常端口、Host 覆盖和凭据查询键；检查具体 http.Transport 的 TLS 配置。阻止重定向跟随，避免正文/会话跨位置重放。不是上传节点或 API 适配。 |
| requester.HTTPGet / Req | HTTPGet 改走 Req；传输错误返回固定脱敏错误，未知正文类型不打印对象；本轮补充 newPolicyRequest 对 URL/方法/构造失败返回固定错误，HTTPGet/Fetch 的响应读取失败经 redactedReadAll 丢弃部分字节与原异常。仅这些已列路径具备错误脱敏设计，不保证整个客户端不泄露。尚未建立证书/超时的精细错误分类，属于剩余工作。 |
| main login Action | 在读取登录参数分支和 RunLogin 前拒绝，返回 verified_identity_binding_unavailable。不会收集密码或运行旧登录流程。CLI 的 reload Before 本身仍可能加载原配置，因此本补丁绝不授权执行完整客户端。 |
| SetupUserByBDUSS / NewUserInfoByBDUSS / NewUserInfoByInput | 入口同样拒绝；不执行 Cookie regex、贴吧初始化或固定 UID 的 force-login。RequireVerifiedIdentityBinding 永远返回错误，不能通过开关变为已认证。 |
| PCSConfig.Save | 非空账号列表在打开/写入配置前拒绝，避免继续保存账号会话；不删除旧文件、不阻止既有加载路径，不声称提供内存认证或完整持久化隔离。 |

依赖链：pcsconfig.NewUserInfoByBDUSS → baidu-tools v1.2.0 tieba.NewUserInfoByBDUSS → 贴吧 HTTP 登录检查/资料查询 → **本仓库 requester.DefaultClient.Req**。补丁并未把 HTTP 地址换成未经核实的 HTTPS 接口，而是在共享请求边界阻止其发送；上层身份入口另行默认拒绝。Baidu-Login 密码流程可能有自己的请求路径，不能只凭此补丁覆盖全部外部依赖；CLI 在 RunLogin 前关闭。任意直接调用 RunLogin 或替换公开 Client/Transport 的程序不在已覆盖路径保证内。

## 身份与资料的明确阻塞

当前没有核实可用、受支持且能可信绑定当前账号的客户端身份接口。故本补丁**没有实现登录成功路径或资料失败降级**，而是保留拒绝。未来只有经验证的身份响应、预期账号匹配、有效凭据与安全传输都成立，才可让可选资料超时降级；不能用跳过查询、固定 UID/用户名或 force-login 替代。此前 Python 模型仅验证这一状态设计，不证明接口存在。

旧 Cookie 格式解析、verbose 日志、明文 JSON 结构仍在被拒绝后的源码中，不是已经全面修复。真实接线前要移除不安全入口、验证依赖和重定向全部路径、制定内存/受限持久化设计及清理、完善安全错误分类；再次审查编译结果。请求层改变会破坏旧 HTTP、下载跳转及带 token 查询的流程，不能当作向后兼容改进或可部署构建。

## 本轮验证与可复现步骤

只针对已审查源码的文件复制到临时目录，检查哈希并 `git apply --check --unidiff-zero`、实际应用补丁，再做静态顺序/拒绝约束检查。没有导入、执行或构建上游程序，没有依赖下载。验证器：

```sh
python3 patches/baidupcs-go-v4.0.2/verify_patch.py --source /path/to/reviewed/fixed-source
```

这不是行为测试：静态文本约束不能证明 Go 编译或运行正确性。主机 PATH 及常规 Go 位置无工具链，**Go 编译、gofmt、六项补丁内 Go 测试均未运行**；没有安装软件绕过限制。待已有审查工具链可用，可在禁止联网的隔离环境仅编译/测试 `requester/security_policy.go` 和 `security_policy_test.go`（标准库、假 RoundTripper，无完整客户端初始化）；之后另行审查实际 requester 包及依赖的构建测试，不自动扩展到完整客户端执行。

本仓库现有 Python 回归工作区 148 项通过，干净归档 144 项通过；这是本项目回归，不是上述 Go 补丁测试。补丁适用性、基线/补丁哈希及静态检查通过，未进行 TLS 握手、真实登录或分享。证据见 `docs/validation/pcs-source-patch-2026-11-09.json`。

此前百度站点安全拒绝继续有效。真实接线前需要允许的渠道，以及指定主机/审查构建、凭据类别/请求目的、存储期限/清理范围和指定对象分享的具体批准；不能通过本补丁、客户端或改变 TLS 绕过拒绝。此次无账户请求、真实凭据、云端对象操作、系统配置变更或新授权。


## 最后一轮审查修订与条件决策

13a20e5 的错误脱敏说明过宽：`http.NewRequest` 失败仍原样返回，`HTTPGet`/`Fetch` 的 `ioutil.ReadAll` 也可能传播原始 reader 错误。本轮补丁将两者移入标准库依赖的固定错误 helper，新增构造错误、响应读取失败（含部分数据）和自定义 transport 错误三项测试，合计六项 **尚未运行**。补丁应用及针对这些修改的静态约束再次通过，不能据此断言 Go 行为正确。

边界仍存在：Req 中 ContentLength/ContentType/Reader 等调用者回调可执行任意代码或 panic；错误 helper 不构成不可信回调沙箱。成功响应正文/响应头不是自动脱敏输出；上层解析、verbose、分享输出和任何绕过 Req 的 Client 调用仍需独立处理。公开可变 Client/Transport/CheckRedirect 可以被调用者替换，独立客户端不继承保护，不能称整个依赖树已被阻断。此补丁是受审入口上的默认拒绝候选，不是可运行安全产品。

身份候选与最终 MVP 决策见[分享调研结论](../../docs/baidu-share-service.md)。当前未具备可用性证据，不选为已可用自动分享后端。有限下一步首先是编译/执行这些源码级离线测试，再决定是否值得准备受控真实身份验证，不能继续用模型或旧 Python 回归替代。

工具链实际检查：PATH 无 `go`；`/usr/local/go/bin/go`、`/usr/lib/go/bin/go`、`/usr/bin/go` 均不存在。基线 go.mod 声明 Go 1.23。下一个最小动作是在本项目主机提供经审查的 Go 1.23 或更高版本工具链，再以 `GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOWORK=off`、隔离临时缓存/目录执行仅两个标准库依赖文件的 `go test security_policy.go security_policy_test.go`；不运行 main 或完整 requester 包初始化，不访问依赖服务器。这是待执行计划，本轮没有下载、安装、容器或切换主机。若需新安装，应先明确官方来源、固定版本、摘要验证与隔离路径并取得批准；此处未给出未经核实的版本或校验和。
