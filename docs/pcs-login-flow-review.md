# BaiduPCS-Go login：真实能力、当前阻拦与最小修复

2026-11-11，回应用户“不能通过login登录吗”。**上游有login命令，并且保留交互式账号密码分支；当前不能直接用，既有我们加的入口限制，也有原登录链的问题，不能混同为百度不支持登录。** 用户问法不等于同意忽略TLS缺陷或保存全部会话材料。本轮仅公开源码审阅和隔离help检查，无真实输入或认证。

## 实际支持的流程

依据固定v4.0.2源码（`225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`），并实际在已安装补丁产物中运行login帮助：

- `BaiduPCS-Go login`：无参数时运行RunLogin，询问用户名及密码，可处理图片验证码、手机/邮箱验证。PasswordPrompt设计为不回显；CLI仍提供password参数，但不能推荐把秘密放进argv/shell历史。没有在本轮用真实终端输入密码或宣称整个TTY流程已验证。
- `login -bduss=… [-stoken=…]`或`login -cookies=…`：导入已签发会话，**不是新的账号密码登录**。帮助例子保留这类参数不代表安全推荐，本轮不要求提供值，也不执行。
- 已审此版本RunLogin没有二维码/扫码分支；不推断其他版本或百度官方客户端没有扫码。
- 上游[当前README](https://github.com/qjfoidnh/BaiduPCS-Go/blob/main/README.md)（本轮blob `84143066a3324206e0da6519b677b4803edcfb22`）明确常规交互登录长期不维护，并推荐Cookie登录。当前保留旧代码不证明服务仍接受，也不证明一定失败；本项目未进行真实认证。

## 请求与保存的实际数据流

`main.go login` → `RunLogin` → Baidu-Login v1.4.1。其NewBaiduClinet在提示账号之前就初始化网络会话：固定HTTPS `wappass.baidu.com`的antireplaytoken、登录JS公钥及根页面/Trace-ID；密码经该库RSA处理后POST到`/wp/api/login`。验证可能访问`/v3/api/auth/widget`、`/passport/authwidget`及`/cgi-bin/genimage`，并使用响应中的verifyURL/loginProxy/u继续请求。不能把这些动态地址说成已审固定端点集合。公钥/时间读取出错存在忽略错误和固定默认值回退，需改为失败停止，不能用应用层RSA替代TLS验证。

取回BDUSS/PTOKEN/STOKEN/Cookie后，SetupUserByBDUSS仍调用baidu-tools v1.2.0的贴吧初始化：**HTTP `tieba.baidu.com/c/s/login`正文带`bdusstoken`，随后HTTP `c.tieba.baidu.com/c/u/user/profile`读取资料**。即便前面的密码POST是HTTPS，这一尾段仍不可直接放开；当前安全补丁的请求边界会拒绝HTTP。不能猜测把URL换成HTTPS就兼容，也不能使用force-login的虚构UID替代身份核验。

原版login挂有After保存钩子。账号结构包含BDUSS、PTOKEN、STOKEN、完整Cookies及其他会话字段；Save序列化普通JSON，**未加密**。默认是当前用户的`.config/BaiduPCS-Go/pcs_config.json`，也可受专用配置目录环境变量/二进制旁旧配置定位影响。新建目录0700、文件0600；这些创建mode不保证修复既有文件的权限，也不构成防符号链接/原子保存。账号密码不在该Baidu账号结构中，不因此保证参数历史/错误输出没有其他泄漏路径。

RunLogin包含最多10轮外层挑战流程，手机/邮箱验证后可能goto重新提交登录；这不是“任何网络错误都盲重试10次”，但真实接线需要按挑战步骤明确请求预算及重提交意图。源码会输出原始errInfo/错误、图片验证码URL及部分手机号/邮箱，验证码图片写入原路径时mode为0777；需收紧为私有保存及固定脱敏错误。用户本人交互不等于授权自动反复登录、向新域发送凭据或持久化所有Cookie。

## 当前安装为何拒绝

| 层 | 实际状态 |
| --- | --- |
| 用户PATH包装器 | 我们自行添加的离线限制；不是百度服务拒绝。现已允许版本、帮助和login帮助 |
| 补丁二进制Action/身份入口 | RequireVerifiedIdentityBinding仍返回未实现错误，发生在原RunLogin/BDUSS初始化之前；单改包装器仍不会登录 |
| 补丁保存入口 | 非空账号列表Save被拒，不能把撤销此保护当作已获准持久化 |
| 上游原流程 | 账号密码分支长期不维护；HTTP携会话、动态验证URL、错误/回退及保存行为均需具体处理。安装无修改原版不能绕过这些问题 |

Baidu-Login实际复用本项目requester，因此已有严格TLS/禁止重定向的补丁会覆盖其此条传输构造；不需要为它再造一套MCP客户端。原版requester曾关闭证书校验，不能恢复。共享请求层补丁也不自动修复RunLogin的所有业务打印、回退或保存行为。

## 已完成的有用调整和可运行命令

安装入口新增精确允许`login --help`和`help login`，仍在真实程序初始化之前建立禁网、临时空配置和文件系统隔离。五项实际检查通过：两个login帮助成功，裸login/带合成password参数/分享命令在进入真实流程前拒绝，合成秘密不回显。没有启动提示输入、读取Cookie/配置或访问百度，凭据文件未创建。

```sh
BaiduPCS-Go login --help
```

它展示真实安装版本的登录选项。`BaiduPCS-Go login`是上游常规交互命令，**目前不要作为已可用步骤交给用户执行**；本轮没有把真实login放开。

## 最小后续改动与需确认的动作

聚焦原登录链，不继续堆叠无关上传/MCP实现：

1. 保持现有TLS/错误脱敏传输，审阅并固定wappass初始化/提交/挑战地址；初始化失败不取默认公钥/时间继续，挑战步骤有界，原始错误/验证码URL不输出。
2. 本人输入限定控制TTY、无回显、禁止password/BDUSS/Cookie argv及环境输入；先确认是否真的要启用旧账号密码流程（上游已长期不维护），而不是把Cookie导入伪称同一件事。无需向聊天发送秘密，也不从其他主机搬会话。
3. 移除登录后HTTP贴吧初始化依赖，用有明确账号语义的安全核验补足；不能伪造UID或把网盘UK直接充当贴吧UID。用户两端同账号的确认保留，精确原文件仍须在境内会话核对。
4. 明确保留方式：临时内存会话需在同一进程继续精确对象/一次分享，退出释放；若用户选择保存，应只在独立私有配置中保留最少凭据，校验所有者/权限、拒绝符号链接并原子保存，不能默认保存完整Cookie集合到旧配置。当前未获得该持久化选择。

**尚未准备好可推荐的真实登录步骤；差距是上述实际代码和凭据保留选择，不是再开一个包装器开关。** 后续本人新认证将接触账号密码/验证码并访问wappass服务，或以本机既有会话做导入，数据流和是否保存须分别明确；用户当前问题不是这些操作的执行批准。本轮没有实际实现/验证新登录的服务兼容性，不用测试fixture冒充已可登录。

来源：[main.go登录分支](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/main.go)、[RunLogin](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/internal/pcscommand/login.go)、[账号配置结构](https://github.com/qjfoidnh/BaiduPCS-Go/blob/225bdd3b6cb298601c4d5ef7104c3e08cd1d692d/internal/pcsconfig/baidu.go)、本地锁定Baidu-Login v1.4.1和baidu-tools v1.2.0源码（只读审阅，无依赖下载/执行）。[源码摘要和实际help检查](validation/pcs-login-flow-review-2026-11-11.json)。
