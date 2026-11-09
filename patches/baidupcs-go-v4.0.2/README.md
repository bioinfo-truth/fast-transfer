# BaiduPCS-Go v4.0.2：默认拒绝的安全补丁候选

基线 `qjfoidnh/BaiduPCS-Go` tag v4.0.2，commit `225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`。这是对实际固定源码的补丁，不是另一个 Python 登录模型。现已完成两个标准库依赖文件的编译和六项离线测试；经后续明确授权补齐固定公开依赖后，完整补丁客户端纯编译已通过；未执行客户端、部署或验证真实能力，不能直接作为可安全登录的发行版。

`security-candidate.patch` 使用零上下文 diff，必须对 `baseline.json` 中逐文件 SHA-256 完全匹配的源码应用，并显式使用 `--unidiff-zero`。不能对未知版本宽松套用。补丁添加六项 Go 离线测试，已在下述隔离范围通过。

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

静态验证器本身不编译/运行 Go，因此输出 `not_run_by_this_static_verifier`；真实执行证据独立保存。用户随后明确批准了本项目隔离官方工具链安装及两个文件的离线编译测试，当前结果见下节；不能把文件级通过扩大为整个补丁包验证。

本仓库既有 Python 回归工作区 148 项/干净归档 144 项是此前结果，本轮没有重复运行替代 Go 检查。

此前百度站点安全拒绝继续有效。真实接线前需要允许的渠道，以及指定主机/审查构建、凭据类别/请求目的、存储期限/清理范围和指定对象分享的具体批准；不能通过本补丁、客户端或改变 TLS 绕过拒绝。此次无账户请求、真实凭据、云端对象操作、系统配置变更或新授权。


## 最后一轮审查修订与条件决策

13a20e5 的错误脱敏说明过宽：`http.NewRequest` 失败仍原样返回，`HTTPGet`/`Fetch` 的 `ioutil.ReadAll` 也可能传播原始 reader 错误。本轮补丁将两者移入标准库依赖的固定错误 helper，新增构造错误、响应读取失败（含部分数据）和自定义 transport 错误三项测试，当时合计六项尚未运行；本次已在下述文件级隔离范围全部通过。补丁应用及针对这些修改的静态约束也已再次通过，仍不能证明完整客户端正确。

边界仍存在：Req 中 ContentLength/ContentType/Reader 等调用者回调可执行任意代码或 panic；错误 helper 不构成不可信回调沙箱。成功响应正文/响应头不是自动脱敏输出；上层解析、verbose、分享输出和任何绕过 Req 的 Client 调用仍需独立处理。公开可变 Client/Transport/CheckRedirect 可以被调用者替换，独立客户端不继承保护，不能称整个依赖树已被阻断。此补丁是受审入口上的默认拒绝候选，不是可运行安全产品。

身份候选与最终 MVP 决策见[分享调研结论](../../docs/baidu-share-service.md)。当前未具备可用性证据，不选为已可用自动分享后端。有限下一步首先是编译/执行这些源码级离线测试，再决定是否值得准备受控真实身份验证，不能继续用模型或旧 Python 回归替代。

## 获准官方工具链安装与文件级 Go 验证

此前 PATH 和三个常规路径无 Go 的检查保留为历史事实；本次用户已明确批准安装。安装前再次确认 Linux x86_64、无同次安装，使用官方 `https://go.dev/dl/?mode=json` 稳定发行元数据，选择 **go1.27.3 linux/amd64**。归档 `go1.27.3.linux-amd64.tar.gz` 为 **70,588,678 字节**，SHA-256 **65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40**；下载入口 `https://go.dev/dl/go1.27.3.linux-amd64.tar.gz` 最终为官方 `https://dl.google.com/go/go1.27.3.linux-amd64.tar.gz`。先验证大小/摘要，再安全解压及执行，没有安装脚本。

隔离根目录为仓库忽略的 `scratch/pcs-go-offline-20261109/`；工具链、归档、HOME/缓存/临时目录和测试二进制都留在其中，没有修改系统 PATH、profile 或其他项目。未覆盖已存在目录。安装前可用 170,824,728,576 字节，解压后 170,457,743,360 字节，编译后检查 170,334,629,888 字节，均大于 5 GiB。它们是检查点数值，不是连续采样最低值。

网络命名空间尝试因 uid_map 权限被系统拒绝，没有重试或调整系统设置。改用已存在的 libseccomp，对每个工具/测试**子进程**施加继承性过滤，禁止 socket/socketpair/connect/bind/listen/accept/accept4/sendto/sendmsg/sendmmsg/recvfrom/recvmsg/recvmmsg；每次 exec 前实测 socket 创建返回 EPERM。仅增加本次进程限制，不修改主机安全配置。过滤器见 `offline_exec.py`（与实际执行副本字节一致）。这是进程网络限制，不是文件系统沙箱；没有把用户配置目录设为输入。

运行以清空继承环境后的显式环境进行：独立 HOME、XDG_CONFIG_HOME、GOCACHE、GOPATH、TMPDIR/GOTMPDIR；GOTOOLCHAIN=local、GOPROXY=off、GOSUMDB=off、GOWORK=off、GOENV=off、GO111MODULE=off、CGO_ENABLED=0、GOTELEMETRY=off。仅工具链绝对路径和局部 PATH，禁止自动下载依赖或工具链。当前操作未读取真实认证配置。

在基线隔离副本应用补丁后，**只传入 `security_policy.go` 与 `security_policy_test.go`**：

1. 绝对路径 `go version` 返回 go1.27.3 linux/amd64。
2. `gofmt -w security_policy.go security_policy_test.go` 成功；最终 patch 已同步此格式化结果。
3. `go test -c -o <isolated>/security_policy.test security_policy.go security_policy_test.go` 成功。
4. 同一网络/配置隔离下运行生成的二进制 `-test.v`，六项全部通过。

复现时须将本目录的 `offline_exec.py` 复制到专用隔离根目录（脚本以自身位置确定工具链/HOME/缓存），通过 `/usr/bin/python3 <isolated>/offline_exec.py <absolute-go-or-gofmt-or-test-binary> <args>` 分别执行上述步骤。脚本不是账户操作授权或通用第三方程序沙箱，不应用来运行完整客户端。编译输入、执行文件摘要、公开安装元数据及逐项结果见 `docs/validation/pcs-go-offline-2026-11-09.json` 和对应测试日志；验证器重新确认最终 patch 的基线/适用性与静态约束。

未执行完整 requester 包、CLI main、身份门/配置包及外部依赖初始化；此前完整源码纯编译曾因依赖缓存缺失停止，后续获准依赖获取后构建成功（末节），未做真实 TLS 握手或百度账户请求。六项只证明已审查 helper/guard 在假请求/内存 transport 下的行为。完整依赖安全、实际身份响应与商用/分享资格仍未确定。当前“保留候选、暂不选作已可用 MVP 自动分享后端”的结论不变。


## 完整补丁的构建条件检查：授权前缺依赖的历史失败

沿用同一个已核验官方工具链，先检查无编译/目标进程运行，工作树仅保留历史未提交实验。新的隔离公开源码副本中应用最终补丁，对全部 **10 个受影响 Go 文件** 执行 gofmt：首次有 8 个文件需格式化，格式化成功，二次 `gofmt -l` 输出为空。最终 patch 已包含这些格式修正；这证明语法可解析/格式一致，不证明类型检查或链接成功。此前编译通过的两个文件摘要未变，因此没有重跑六项测试。

检查固定基线的 go.mod/go.sum：go.mod 声明 **34 个固定模块**（直接和 indirect），专用 GOPATH 的模块源码缓存没有这些包。模块清单、固定版本、公开来源地址和现有 go.sum 的 h1 记录已保存到 `docs/validation/pcs-package-build-2026-11-09.json`；这 34 项不一定是完整传递依赖闭包，不能将首次报错清单当成全部所需依赖。

使用同一禁网子进程 wrapper 的局部副本，仅将 `GO111MODULE=off` 改为 `on` 以读取上游 go.mod，其他清空继承环境、独立 HOME/缓存、GOTOOLCHAIN=local、GOPROXY=off、GOSUMDB=off、GOWORK=off、CGO_ENABLED=0 和 seccomp 拒绝保持不变；在固定源码根目录执行：

```text
go build -mod=readonly -o <isolated>/pcs-never-execute .
```

退出码 **1**：15 个模块被首次报告缺失，具体导入位置均返回 `module lookup disabled by GOPROXY=off`。例如 urfave/cli v1.22.5、tablewriter v0.0.4、liner v1.2.2、json-iterator v1.1.12、Baidu-Login v1.4.1、baidu-tools v1.2.0 和 dnscache 固定伪版本。日志中 Go 的 “downloading” 行表示尝试解析缺失缓存，**不表示实际下载成功**；代理关闭且子进程 socket 被拒绝，没有获得依赖、没有生成客户端二进制。未运行包初始化或任何目标程序。失败日志见 `docs/validation/pcs-package-build-2026-11-09.txt`。

确定剩余阻碍是依赖来源/获取范围和模块闭包审查，而非再次安装 Go。此次许可不包含新依赖下载，因此停止同类构建尝试，不使用 stub、用户 HOME 缓存、其他设备或容器替代。当前可独立做的补丁应用、语法/格式、现有缓存和声明依赖核对均已完成；没有已知可在当前空缓存中继续完成的相关包纯编译步骤。

若继续，下一动作需具体批准：只为该固定源码取得已列固定版本的公开依赖归档及必要 go.mod/传递依赖元数据，来源限定维护者官方公开仓库或经确认的 Go 模块发行服务，进入本项目隔离模块缓存，按已有 go.sum 验证且不更新版本/不执行安装脚本；审查闭包后再恢复禁网纯编译。新增代码供应链/依赖完整性需核验，编译成功也不授权执行客户端或账户操作。若依赖图要求未列版本或 go.sum 缺失，应先列差异，而非自行扩大获取范围。**未代为下载或申请真实认证。**


## 获准固定依赖获取后：完整客户端纯编译成功

用户随后明确批准“仅取得锁定版本公开依赖和必要元数据，核验原 go.sum 后断网编译，不涉及秘密”。本次在同一隔离目录完成，没有安装新工具链、读取用户缓存、登录百度或执行目标程序。

获取分两部分：

- 34 个 go.mod 声明模块的固定源码归档和必要 `.info`/`.mod`。每次明确 `module@version`，在独立最小临时模块中执行 `go mod download -json`，逐项核对原 go.sum 的 `Sum` 与 `GoModSum`；所有 34 项通过，还记录各 ZIP 的 SHA-256/大小。
- 离线解析旧传递依赖图需要额外 **185 份 go.mod 文本**。仅对离线构建明确报出的模块/版本取 `.mod`，发送请求前要求原 go.sum 已有该版本的 `/go.mod h1`；按官方工具链源代码 `dirhash.Hash1` 的单文件 go.mod 算法核验后才放入缓存。没有为只锁定元数据的模块下载 ZIP，不升级选定版本；这不是 185 个新增源码依赖。完整范围见执行 JSON。

网络获取阶段从空继承环境启动，仅使用 `https://proxy.golang.org`，不设置 direct/其他代理回退；Go 使用 GOAUTH=off、GOVCS=*:off、GOENV=off、GOTOOLCHAIN=local、GOSUMDB=off 和专用 HOME/缓存，curl 元数据获取使用 `-q` 禁止读取 curl 配置。只发送公开模块路径/版本，无用户原话、会话标识、私有仓库认证、Cookie 或令牌。使用标准 TLS，不改系统配置。go.sum 仅作为原固定内容的完整性依据，未访问 sumdb；这不是漏洞审计或新的来源认证保证。

每次补充必要元数据后恢复原子进程 seccomp 禁网，以 `GOPROXY=off`、`GOSUMDB=off`、`GOWORK=off`、`GOTOOLCHAIN=local`、GO111MODULE=on、CGO_ENABLED=0 和独立配置/缓存继续 `go build -mod=readonly -o <isolated>/pcs-never-execute .`。中间模块图解析失败属于同一已知缓存缺口的分步核验；最终完整根包编译和链接 **退出 0，输出为空**。全部 go.mod/go.sum 字节未变。

产物为 20,870,517 字节，SHA-256/实际编译输入摘要见 `docs/validation/pcs-full-build-2026-11-09.json`。只用 Go 工具读取构建元数据，**从未执行客户端二进制或依赖初始化/测试**；工具链、缓存、源码副本和产物都保留于忽略的 scratch 隔离目录，未提交二进制。最终可用磁盘检查点 169,741,111,296 字节（大于 5 GiB）。没有重跑旧六项测试充当进展。

现在可确定固定源码及安全补丁在该工具链/锁定依赖下能完整构建，先前“缺依赖不能编译”的阻碍已解除。但身份门仍故意默认拒绝；真实身份响应/账号访问、请求链的运行行为、真实 TLS 握手及分享能力均未验证，依赖未作全面漏洞审计。**构建成功不等于登录修复，更不等于 MVP 自动分享后端可用。** 后续若准备真实认证，仍须先有允许渠道、可信身份绑定设计与明确的主机/构建/凭据类别、请求/存储/清理范围批准；已有站点拒绝有效，不通过本次产物绕过。


## 实际包回归的后续证据

不再仅测试独立 helper：实际 requester 包编译及其经过审查的 6 包非标准库初始化闭包在 seccomp + Landlock 限制下执行，七项新回归通过，覆盖真实构造/Req/Fetch/HTTPGet 和文件/网络隔离边界。配置包的身份门/持久化两项测试只编译、不执行，因为其 74 包传递初始化尚未全面审查。没有运行 main、真实登录或分享，也没有新增依赖；原有六项测试未重复。测试源码、执行 wrapper、初始化范围和精确限制见[实际包回归说明](regression/README.md)与 `docs/validation/pcs-package-regression-2026-11-09.json`。这不改变真实身份默认拒绝或 MVP 后端未具备可用性证据的结论。


## 配置包初始化缺口已在两项假值路径解除

进一步审查实际选中的 74 包初始化：GetConfigDir 使用绝对隔离目录提前返回；PCSConfig.init 是有 receiver 的普通方法，不自动加载配置；protobuf binaryHash 只读取受允许的当前测试二进制，其他构造/环境/注册路径受已记录限制。专用目标白名单、Landlock 和 seccomp 在目标初始化前生效后，实际配置包两项测试运行通过，证明身份入口默认拒绝及假账号 Save 在建文件前拒绝；运行后 HOME 仍为空。当前完整构建、requester 七项及配置两项均有证据，但没有真实身份/登录/分享。详情见[配置审查与执行说明](regression/README.md)和 `docs/validation/pcs-config-runtime-2026-11-09.json`。


## 身份/分享链路契约候选与宽容解析缺口

后续在实际 baidupcs 包中以假响应确认 UK 和 ShareSet 的解析边界：两个特征测试/十二子场景复现了缺成功码、非正身份、缺分享 ID 与非法链接等接受行为。测试源码及专用 runtime wrapper 在 `contracts/`，设计与阶段范围见[身份/对象/分享方案](../../docs/pcs-identity-share-plan.md)。普通 go test -c 遇到已有 PrepareBDStoken int→string vet 诊断，特征测试明确 -vet=off 编译后在原级别 Landlock/seccomp 下运行；未更改真实身份门或实现适配器。此证据表明不能直接把原 parser/CLI 当成可信交付，不代表真实服务验证或资格通过。
