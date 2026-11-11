# 本人一次性内存登录：已准备，未真实认证

2026-11-11。用户要求安装后测试并询问直接login；本轮在已授权的软件开发范围内，继续修复实际流程，而非仅解释离线wrapper。**新增并安装`BaiduPCS-Go login --session-only`作为登录兼容性测试入口，未在本轮启动本人输入或认证请求。** 这是本项目的新子流程，不是上游原有参数、无修改发行版或已验证可在线登录的保证。

## 实际完成的改动

- 原上游裸login保持未放开；新入口不调用PCSConfig、SetupUserByBDUSS、NewUserInfoByBDUSS或贴吧初始化。固定请求策略拒绝任何HTTP/Tieba/share端点，因此不是把旧HTTP URL换成未经验证的HTTPS地址。
- 独立Go companion复用锁定Baidu-Login v1.4.1的WAP表单及bdcrypto算法，仅替换必要的网络/会话编排，不引入MCP客户端或其他网盘后端。旧账号密码协议仍长期不维护，其应用层RSA表示按上游保持，不冒称已更新为现代认证协议；保护传输依赖严格TLS，在线兼容性未知。
- 只允许五类固定HTTPS请求：wappass的antireplaytoken、固定登录JS、根页面的Trace-ID响应头（不读页面正文）、`/wp/api/login`，以及pan的`/api/user/getinfo?need_selfinfo=1`。公钥/时间/Trace-ID缺失、格式不符或传输失败即停止，没有默认公钥/时间兜底。密码长度超出实际公钥编码容量时在提交前拒绝。
- 系统信任根、证书/主机名校验、TLS至少1.2；不接代理、任意Host/SNI、重定向或响应里的verifyURL/loginProxy/u。DNS只接受公网结果并为每个固定主机选择一个地址，不尝试替代地址；禁keepalive/HTTP2以避免复用连接重放，单次会话45秒预算。真实POST至多一次，可能已发后失败为`authentication_outcome_unknown`，不会自动再提交。
- 收到手机/邮箱或图片验证码要求后，只给固定状态/错误码，**不发短信、不抓验证码图、不跟随验证URL、不重进登录循环**。验证码续办未实现，不能把当前准备称为完整修复全部交互登录。
- 登录返回的Cookie只留在Go进程内存；随后只把BDUSS发给固定pan身份接口，不转发完整Cookie集合，不采集贴吧UID或将网盘UK伪装成贴吧UID。成功码但无有效Cookie、缺失/异常身份信封均不宣称已验证登录。
- Python前端要求控制TTY，账号和密码均不回显；无stdin回退、argv/env秘密输入或调试输出。凭据仅经本机私有stdin管道送到固定哈希helper；清空子进程环境/额外FD、禁core dump，退出不导出Cookie。只输出固定状态、布尔和有界计数，服务器errmsg/原始响应/异常不反射；错误码若等于输入秘密也抑制。

## 明确的数据流与保留方式

本人终端隐藏输入用户名/密码 → 本机Python内存 → 本机Go helper私有管道 → 严格TLS向`wappass.baidu.com/wp/api/login`提交一次上游协议编码的密码 → 内存Cookie jar → 只取BDUSS经TLS送`pan.baidu.com/api/user/getinfo`核对身份响应 → 只输出脱敏结果并退出。

无OAuth、refresh、新应用授权、文件访问、上传、分享、服务购买或其他接收人。VPS令牌/原Cookie不迁移，原NCBI样例不动。

**应用不写入任何密码、BDUSS、PTOKEN、STOKEN或完整Cookies文件，不调用旧JSON配置保存。** helper使用临时空HOME、无继承代理/凭据环境，安装的二进制、manifest、LICENSE不是认证存储。真实默认pcs_config.json仍不存在。会话Cookie可能具备账号级权限；本程序限制自己的使用范围，不改变百度授予的会话权限。内存对象/字符串无法承诺安全擦除；即使本机不保存，未来成功登录创建的服务器会话可能在进程退出后继续有效，本流程不自动调用注销/撤销。退出后无法用本次会话执行下一条share命令；后续若要同会话分享，应先在同一进程接入精确原对象和已有单次意图核验，而不是默认保存全部认证材料或让用户反复登录。

本轮没有采用持久化方案。若以后确有必须保存的需求，应另行具体批准“同机独立0700目录/0600文件、最少凭据类别、非加密还是经审阅的密钥存储、到期/清理及撤销方式”，不可沿用上游保存全Cookie集合的默认动作。当前不因安装授权获得保存秘密的许可。

## 已验证及没有验证

| 检查 | 结果及边界 |
| --- | --- |
| Go合成/禁网 | 13项通过，零失败/跳过；覆盖成功候选、初始化失败不提交、无fallback、重复JSON/异常信封、未知不重发、挑战不续办、Cookie最少转发、账号不匹配、秘密回显抑制、输入长度及固定路由 |
| 本地真实TLS | 4项通过（含错误主机/不受信任链两个子情形）；只连本地生成证书的测试服务和虚构账号，验证正确TLS、证书拒绝、重定向不跟随、服务端读完POST后丢响应仍只提交一次。不是百度认证 |
| 前端生成凭据PTY | 6项禁网通过；不回显、恢复终端、取消/超时/无TTY拒绝、argv拒绝及结果脱敏 |
| 安装无凭据检查 | 6项通过：版本/原login帮助/session帮助可运行；无TTY的session在输入前拒绝；裸login和秘密参数拒绝。没有启动真实输入或触发百度请求 |
| 真实账户/原对象/分享 | 全部未执行。无本机已有登录这一事实保持；用户确认两端同账号作为背景，前端此阶段不自动带入独立旧账号指纹，因此即使以后pan接受本次身份，也不等于已核对原账户/原文件 |

源码在固定缓存上禁网编译，无新依赖下载；运行环境为linux/amd64。companion和前端/launcher均按安装manifest哈希验证，原候选CLI二进制不变；LICENSE/NOTICE保留。Go合成与本地TLS分别记录，不能把helper存在或本地测试通过视作百度仍支持旧WAP流程。

[准备及安装摘要/源哈希](validation/pcs-login-session-preparation-2026-11-11.json)、[Go禁网日志](validation/pcs-login-session-offline-2026-11-11.txt)、[本地TLS日志（已去掉本地动态地址）](validation/pcs-login-session-local-tls-2026-11-11.txt)、[PTY禁网日志](validation/pcs-login-session-frontend-2026-11-11.txt)、[Go源码](../patches/baidupcs-go-v4.0.2/login-session/main.go)、[本人输入前端](../scripts/baidupcs-go-login-session.py)。

## 本人操作与具体待批准动作

现在可无凭据查看：

```sh
BaiduPCS-Go login --session-only --help
```

若明确批准“由本人在境内主机新建一次账号密码登录，仅内存，固定wappass提交一次及pan身份查询，不保存、不续办验证、不分享”，本人可在该主机的交互终端运行：

```sh
BaiduPCS-Go login --session-only
```

先阅读显示的目标和会话范围，隐藏输入确认词`LOGIN-SESSION`，再隐藏输入账号与密码；不要在聊天、命令参数、环境变量或另一主机传递凭据。出现验证码、拒绝、TLS错误或未知结果即停，不自行放宽或反复运行。该入口不使用已拒网页，不把新CLI代码或用户同意当作绕过任何现有安全阻断的依据；后续如遇新的明确拒绝立即停止。

本轮只完成准备，无真实认证。需要用户决定的是上述具体新登录/身份查询动作，**不请求批准默认持久化或新分享**；也不再泛问是否想生成链接。
