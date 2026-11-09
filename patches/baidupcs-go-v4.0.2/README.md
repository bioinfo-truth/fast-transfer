# BaiduPCS-Go v4.0.2：默认拒绝的安全补丁候选

基线 `qjfoidnh/BaiduPCS-Go` tag v4.0.2，commit `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`。这是对实际固定源码的补丁，不是另一个 Python 登录模型。尚未编译、部署或验证真实能力，不能直接作为可安全登录的发行版。

`security-candidate.patch` 使用零上下文 diff，必须对 `baseline.json` 中逐文件 SHA-256 完全匹配的源码应用，并显式使用 `--unidiff-zero`。不能对未知版本宽松套用。补丁同时添加三项 Go 内存 transport 测试；它们本轮未运行。

## 实际变更与调用链

| 路径/函数 | 补丁行为 |
| --- | --- |
| requester.NewHTTPClient / lazyInit | 构造时初始化受保护 transport；真实 http.Transport 恢复标准证书/主机名校验，最低 TLS 1.2；CheckRedirect 全部拒绝。构造只设置对象，不发请求。 |
| requester.SetHTTPSecure / dialTLSFunc | 原来强制跳过校验的开关和备用 TLS 路径均改为严格校验，不提供关闭验证的兜底。 |
| guardedTransport.RoundTrip | 在任何底层传输前拒绝 HTTP、非允许域后缀、userinfo/fragment/异常端口、Host 覆盖和凭据查询键；检查具体 http.Transport 的 TLS 配置。阻止重定向跟随，避免正文/会话跨位置重放。不是上传节点或 API 适配。 |
| requester.HTTPGet / Req | HTTPGet 改走 Req；传输错误返回固定脱敏错误，未知正文类型不打印对象。不把带秘密的 URL、正文或错误原文向调用者传播。尚未建立证书/超时的精细错误分类，属于剩余工作。 |
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

这不是行为测试：静态文本约束不能证明 Go 编译或运行正确性。主机 PATH 及常规 Go 位置无工具链，**Go 编译、gofmt、三项补丁内 Go 测试均未运行**；没有安装软件绕过限制。待已有审查工具链可用，可在禁止联网的隔离环境仅编译/测试 `requester/security_policy.go` 和 `security_policy_test.go`（标准库、假 RoundTripper，无完整客户端初始化）；之后另行审查实际 requester 包及依赖的构建测试，不自动扩展到完整客户端执行。

本仓库现有 Python 回归工作区 148 项通过，干净归档 144 项通过；这是本项目回归，不是上述 Go 补丁测试。补丁适用性、基线/补丁哈希及静态检查通过，未进行 TLS 握手、真实登录或分享。证据见 `docs/validation/pcs-source-patch-2026-11-09.json`。

此前百度站点安全拒绝继续有效。真实接线前需要允许的渠道，以及指定主机/审查构建、凭据类别/请求目的、存储期限/清理范围和指定对象分享的具体批准；不能通过本补丁、客户端或改变 TLS 绕过拒绝。此次无账户请求、真实凭据、云端对象操作、系统配置变更或新授权。
