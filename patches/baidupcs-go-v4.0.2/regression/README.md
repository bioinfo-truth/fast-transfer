# 实际包路径回归与运行边界

2026-11-09，仅固定补丁源码、已核验缓存及固定假值，无账户请求或真实凭据。不是独立 Python 模型或仅传入两个 helper 文件。

## 编译和执行结果

| 项目 | 编译 | 执行 |
| --- | --- | --- |
| 实际 requester 包及其初始化 | `go test -c ./requester` 通过 | 仅 `-test.run=^TestFT` 七项通过 |
| 实际 internal/pcsconfig 包 | `go test -c ./internal/pcsconfig` 通过 | **未运行**：74 个非标准库传递包的完整初始化审查未完成 |

将 `requester_regression_test.go` 复制为固定隔离副本 `requester/ft_regression_test.go`，`config_regression_test.go` 复制为 `internal/pcsconfig/ft_regression_test.go`，使用已有受审工具链/缓存、同一断网编译 wrapper 生成两个不同测试二进制；没有构建或执行新的 main。只编译不执行配置测试；不能把它们记为身份/持久化行为测试通过。

七项实际请求层测试覆盖：NewHTTPClient 默认 guardedTransport、SetHTTPSecure 两档均不能关闭证书保护、Req 的 HTTP 前置拒绝/构造和 transport 错误脱敏、实际 http.Client 重定向 hook 不跟随、Fetch/HTTPGet 部分读取失败不泄露、仅内存成功响应，以及网络/越界文件/符号链接边界。没有真实证书握手，fake transport 不证明网络/服务协议兼容性。

配置测试已准备 malformed 假输入在 regex/用户初始化前被身份门拒绝，BDUSS/force-login 入口拒绝，以及带假账号的 Save 在创建文件前拒绝。全部仅为**编译通过、未执行**。已编译两个测试包不等于运行它们的初始化。

## 初始化审查范围

通过禁网 `go list -deps -json` 取得构建选中的文件，未执行目标包。requester 的非标准库闭包为 6 包：requester、rio、expires、cachemap、dnscache、singleflight。审查初始化路径为构造内存 HTTP/cookiejar/TLS 对象、缓存槽/锁和未启动 DNS Resolver；DNS 查询、代理环境解析均在调用路径中，不在这些初始化构造中。没有导入 pcsconfig 或 main。现有 requester 测试文件无 TestMain/init，运行 filter 排除上游测试和旧六项 helper 测试；这不是整个源码依赖的正式安全审计。具体选中文件摘要见验证 JSON。

配置包则在全局初始化调用 GetConfigDir，可能探查可执行文件旁的旧配置或创建 HOME 目录；NewConfig 仅分配对象，但 Init/Reload 才会加载文件。其 74 个非标准库闭包含 JSON/reflect、protobuf 注册、终端/颜色和环境初始化，不能只看 func init 或设置 HOME 就认定安全。本轮不执行配置测试，下一步应完整核对传递全局变量构造及其副作用，再评估同级隔离下只运行两项测试。不需要新真实凭据，也不应把这一步替换为登录。

## 运行时文件系统与网络限制

`restricted_test_exec.py` 是与实际执行相同的受审 wrapper，复制到同一 scratch 隔离根目录后使用；脚本只允许运行该目录下 `requester-regression.test`，不能传入配置测试或客户端。由 `/usr/bin/python3 -I -S` 启动，launcher 环境只含固定 PATH，stdin 指向 /dev/null，关闭额外继承 FD；测试目标使用显式 HOME/XDG_CONFIG_HOME/TMPDIR、绝对空配置目录和两个自建假文件探针，不继承个人环境或配置。

在目标测试初始化**之前**启用：

- 子进程 seccomp 拒绝 socket/socketpair/connect/bind/listen/accept/accept4/sendto/sendmsg/sendmmsg/recvfrom/recvmsg/recvmmsg。
- Landlock ABI 8，处理文件系统 v1 权限及 REFER/TRUNCATE：scratch 内容读写允许，仅指定测试二进制允许 execute；隔离目录外文件内容读写/目录列举拒绝。没有修改系统设置或使用容器/另一个设备。
- wrapper 和 Go 测试均验证 socket 返回 EPERM，以及读取自己新建的目录外假文件/指向它的符号链接返回 EACCES。探针只含 FAKE_ONLY 公开假数据；父进程随后删除自己创建的假文件，没有读取真实账户文件。

Landlock 不是完整虚拟机：不隐藏所有路径元数据、不是 CPU/内存限制，也不撤销已打开 FD 的所有能力。该次额外 FD 关闭、stdin 为空设备、stdout/stderr 为日志管道；规则不为不可信任意代码提供通用授权。标准库初始化受上述限制，网络/真实文件访问失败不能用放宽规则重试。已有站点安全拒绝不变。

## 当前明确结论

新增了真实请求层包初始化及调用路径的受限运行证据，超出此前 helper-only 六项验证；没有验证可信身份接口、配置完整初始化、真实账号权限或自动分享。补丁仍默认拒绝真实身份入口，因此尚不能选作已可用 MVP 后端。此轮无新依赖/版本、客户端运行、登录、分享或持久账户访问。任何未来真实账户测试仍须先具备允许渠道并对主机/构建/凭据类别、请求/存储/清理和对象范围明确授权。

## 配置初始化具体审查及两项测试已运行（后续状态）

此前“74 包初始化未审查、配置测试仅编译”是上一阶段记录，本次已按实际构建选中的 GoFiles 完成针对两项假值测试的初始化路径审查，并在目标初始化前启用限制后运行，两项全部通过。不是因为包数量少或多就判安全，也不是全面依赖漏洞审计。

审查使用 `init_scan.go`：Go AST 提取包级变量的调用表达式和**无 receiver 的** `func init`，随后追踪构造函数及其 I/O 分支；方法 `.init()` 不属于自动初始化，闭包/工厂注册不等于立即调用。扫描器只依赖标准库，在原隔离环境编译/运行，读取固定公开源码；未执行目标包。实际选中文件摘要完整保存到 `docs/validation/pcs-config-runtime-2026-11-09.json`。扫描结果只是审查清单，不构成完整调用图或形式证明。

| 初始化路径 | 具体判断与限制 |
| --- | --- |
| pcsconfig.GetConfigDir | 显式绝对 BAIDUPCS_GO_CONFIG_DIR 会提前返回，避免旧配置探查及 HOME mkdir 分支。测试启动器设置新的隔离空目录路径。 |
| pcsconfig.Config=NewConfig(...) | 只分配结构，不加载文件；`.init()` 有 receiver，是普通方法，Init/Reload 未被调用。测试确认默认 configFile=nil、账号列表为空、目标配置不存在。 |
| protobuf detrand.binaryHash | 会读取当前测试二进制的若干片段和尺寸，不能误称整个初始化“纯内存”；该二进制在 Landlock 内容读取白名单内，没有账号文件输入。 |
| osext | 本工具链选中 osext_go18.go，调用 os.Executable 获取自身路径元数据；没有执行外部程序。 |
| color/runewidth/verbose | 读取 TERM/NO_COLOR/locale/verbose 等目标显式环境和标准输出描述符。目标环境未继承个人值；stdout/stderr 为管道，verbose 关闭。 |
| concurrent/reflect2/jsoniter | context、map、mutex、反射缓存和工厂构造；NewUnboundedExecutor 不启动 worker。已注册回调未因注册就执行。 |
| protobuf/transfer 注册及内置默认值 | 固定嵌入描述符/表的内存解码和类型注册；异常可输出静态错误或退出，不引入账户输入。未发现这些具体初始化路径需放宽网络/文件权限。 |

专用 `restricted_config_test_exec.py` 与 requester wrapper 分开，**只准该隔离根目录的 config-regression-reviewed.test**，并将测试 filter 固定为两个确切名称。新的 HOME/TMPDIR 在运行前独占创建；Landlock 白名单和 seccomp 禁网在 exec/目标初始化之前生效，Python 使用 -I -S、清空继承环境、关闭额外 FD、stdin=/dev/null。没有放宽文件或网络保护。

wrapper 及两项 Go 测试均验证目录外自建假文件/符号链接读取被拒绝、socket 返回 EPERM。每项还验证默认配置没有加载账号；身份测试覆盖 malformed 假 Cookie、BDUSS、强制身份入口全部拒绝，Save 测试确认含假账号的配置在创建文件之前返回拒绝。运行后独立 HOME 仍为空。仅测试二进制/harness 及审查过的传递初始化执行，**没有运行客户端 main、配置 Init/Reload、成功账号保存或任何真实登录/分享**。旧 requester 七项、helper 六项及 Python 测试未重复。

当前新增确定结论是实际配置包的拒绝门和假账号保存前置防护有效，先前这两项“只编译”缺口已解除；真实身份入口仍默认拒绝，因此不能据此认定自动分享可用。下一阶段如需真实认证，仍须先确认允许渠道和可信身份契约，并对具体主机/构建、凭据类别/用途、请求/保存/清理及对象范围取得明确许可；不得通过任何客户端绕过既有站点拒绝。
