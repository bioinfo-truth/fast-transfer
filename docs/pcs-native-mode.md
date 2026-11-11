# 恢复原生BaiduPCS-Go模式

2026-11-11。用户明确选择原生模式并要求切回，默认`BaiduPCS-Go`入口现直接运行基于固定上游v4.0.2源码的本机构建，恢复原生SetupUserByBDUSS、配置保存及分享命令。自定义密码登录/单次分享companion保留为历史实验，但不再作为默认入口，不再使用`--session-only`命令。未真实登录、读取既有凭据或创建分享。

## 本人登录

```sh
BaiduPCS-Go login --bduss-prompt
```

按用户偏好，在本人交互终端先粘贴BDUSS回车，再粘贴STOKEN回车，两项均隐藏输入且不能为空；随后交给原生SetupUserByBDUSS，按原生方式保存本机配置。`--bduss-prompt`是局部输入选项，不是新的认证协议。

完整Cookie方式仍可用`BaiduPCS-Go login --cookies-prompt`：在本人交互终端粘贴Cookie并回车。`--cookies-prompt`是本项目新增的小选项：隐藏输入后把Cookie交给原生登录函数，不走自定义认证服务，不要求账号密码。Cookie不在命令参数或shell历史中。原生`login -cookies=...`和BDUSS参数仍保留，但它们会把凭据放入进程参数；不建议粘贴秘密到命令行。不要向聊天或公开文档提供Cookie。

原生模式会将Cookie/BDUSS等以明文保存在本机配置中，而非仅内存会话。默认配置目录由原客户端决定（Linux通常为`~/.config/BaiduPCS-Go/`，显式配置环境变量可能改变位置）。入口umask077，原生新目录0700、配置文件0600；已有配置不会由安装步骤读取、迁移或覆盖。安装检查使用临时空配置，不能证明真实Cookie有效。

## 保留的局部安全修正

- requester的TLS证书及主机名校验保持启用，TLS最低1.2；原生配置开关不能重新关闭证书校验。
- 固定依赖baidu-tools的贴吧HTTP地址改为HTTPS，保留原接口、身份语义及原生调用流程；在线兼容性未知，证书失败不降级回HTTP。
- requester.Req拒绝HTTP，默认客户端不自动跟随重定向。不是整个第三方程序所有功能的完整安全审计。
- 入口设置umask077并关闭core dump。没有替换分享协议或取消原生身份校验，不启用force_login_username。

这仍是有少量本地安全修正的构建，不是无修改官方发行二进制，版本显示v4.0.2-dev。未查询最新版，也不声明这是最新上游发布。

## 验证与复现

构建及requester/pcsconfig的go vet通过；两个本地测试验证不受信任证书拒绝、受信任本地证书成功、Req明文请求拒绝，以及默认重定向拒绝。三项禁网临时空配置检查通过：版本、login帮助（包含cookies-prompt）、share帮助。不使用真实Cookie，不进行真实网络登录或分享。

固定上游提交`225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`应用`patches/baidupcs-go-v4.0.2/native/native.patch`；复制固定依赖baidu-tools v1.2.0到源码`local-baidu-tools`，应用`baidu-tools-https.patch`并添加只有module声明及go1.23的go.mod。使用既有固定离线依赖和Go1.27.3构建。测试源`native_security_test.go`复制到requester后单独编译，只运行TestNativeSecurity前缀，避免运行上游联网测试。产物摘要及无凭据检查见`docs/validation/pcs-native-switch-2026-11-11.json`。

先前原样例私有期望清单保留，未重复上传。切换模式不代表账号/对象已在境内核实或分享已成功；后续仍需针对原文件核对后分享，未知创建结果不得盲目重发。原生命令自身没有前一实验companion的持久单次意图保护。

分别输入选项已编译安装并通过禁网帮助检查。合成PTY确认BDUSS/STOKEN提示顺序、关闭回显和测试BDUSS不出现在终端输出；空STOKEN在调用原生登录前返回。未使用实际凭据或执行真实登录。
