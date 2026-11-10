# 用户本人在服务器终端输入短期令牌

2026-11-10：新增 `tools/mcp_terminal_readonly.py` 与 `fast_transfer/mcp_terminal.py`。这是安全交互、仅发现工具及受限只读入口；**本轮没有启动OAuth、生成/读取真实令牌、访问官方服务或部署到VPS**。实现入口不等于用户已授权读取/提交凭据，不能要求用户在聊天贴令牌。

## 当前可以在哪运行

代码和入口目前仅在当前项目执行主机的评审工作区，已经核实 `/usr/bin/python3` 为 **Python3.14.4** 并执行入口 `--help`；**原海外VPS尚未部署**。下面命令是在该工作区根目录运行的用法，不能直接假定VPS已有相同路径或程序。若决定在VPS操作，需要先明确允许部署的位置和代码版本，不先让用户在不存在的入口输入令牌。

最小第一步是 **仅发现工具**，不需要账号、文件ID或期望文件，用户无需猜任何字段：

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tools/mcp_terminal_readonly.py --discover-only
```

它先要求隐藏输入 `DISCOVER-ONLY`，再出现短期access_token的隐藏提示。该模式只发initialize、initialized通知及tools/list，账号/文件/分享RPC在会话层禁止，不创建Job。只输出计数、三个已知工具存在与候选schema匹配布尔项，不复制服务端schema描述、属性名、default或任意原文，防止响应回显敏感数据。工具出现也不证明账号/应用权限。选择执行主机及向官方端点提交token的许可仍需明确；实现和提示本身不是授权。

## 后续精确只读核验的步骤与前提

1. 在原服务器的可信交互终端中使用已审阅的项目版本，具备Python标准库ssl/termios、系统CA和前台控制TTY。终端不能有会记录按键输入的录制机制；本程序只能关闭回显，不能控制终端软件、服务器管理员或系统级记录。不要从聊天/自动化工具代输，也不要以管道、here-document或重定向提供令牌。
2. 准备一个**不含任何令牌/密码**的私有期望JSON文件，当前用户所有、普通文件、无符号链接或硬链接、权限0600。必须仅含ExpectedObject字段：`task, account, application, fsid, path, size, md5, sha256, mapping_sha256`，值从原可信私有任务/回读收据逐项取得，不扫描网盘或旧秘密，不使用合成测试对象替代。字段是核对期望，不是应用权限证明。
3. 期望记录准备完成后，在仓库根目录执行下列命令，文件路径替换为该私有期望记录。参数和文件中均不要放令牌；命令本身不会申请/刷新授权。

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tools/mcp_terminal_readonly.py \
  --expectations /absolute/private/expected-object.json \
  --read-only
```

4. 入口先说明固定官方目的地与范围，要求用户在隐藏输入中键入 `READ-ONLY`。然后在第二个隐藏输入提示中由用户本人输入已有、已明确获准用于本次官方MCP的短期access_token，按回车。**不要将token写进命令、环境、.env、历史、脚本、记录文件或聊天。** 本次没有生成新token，也没有提供OAuth重授权流程。
5. 输入各有60秒窗口，可用Ctrl-C取消、Ctrl-D结束；支持删除键和Ctrl-U清空。程序只返回脱敏状态/schema结构，未知或不匹配即停，不自动重试。非交互、无前台控制TTY或关闭回显失败均拒绝，不退回普通stdin/getpass回显输入。标准输入/输出/错误均需TTY，不能为保存输出而绕过检查。

## 如何准备期望记录，不让用户猜文件ID

输入入口已经可用，但本轮没有定位或读取原私有收据。用户只需明确提供**原成功回读记录所在的确切位置**，不用在聊天发文件内容、账号、fsid或token；不扫描服务器目录去找。经确认后由受审提取步骤在原位置读无token的可信记录，生成0600期望文件，不输出私有标识。

已核对原运行代码：成功恢复结果文件名为 `recovery-result.json`，可提供job_id、target、verified_object_id及readback长度/双哈希；源收据是 `source/.receipts/0.json`。原 `recovered-session.private.json` 保存账号SHA256指纹及原任务关联，**不是原始uk**，不能反推uk，也不能用它伪造当前ExpectedObject.account。若没有独立可信的原始uk记录，精确只读模式暂不可执行，需另行明确补齐可信账号依据/审阅指纹比较接口，不能让用户猜。应用从原已核实的Xtransfer范围取值；mapping_sha256必须对应可信原任务mapping，不能随意填或把新的摘要冒称原Job证据。

因此仅凭公开的1,379,902字节/双哈希不足以生成全部期望字段；当前不提供会替换对象或伪造缺项的自动生成器。仅发现工具模式不受这些文件定位缺口阻挡。原收据路径尚未提供，最终期望文件尚未生成；下面精确只读命令是后续用法，当前不可越过该前提。

## 实际可执行范围

短期token只留进程内，交给固定官方 `https://mcp-pan.baidu.com/sse` 的URL查询认证；系统CA与域名校验、同主机443、精确 `/message` + `sessionId`、公共地址固定、无代理/重定向/自动重试不变。URL和原始异常不打印，无LLM或子进程调用，不读已有凭据/环境/浏览器，不写token文件。客户端脱敏不能控制官方服务端是否记录查询URL，用户应在提交前了解这一数据流。

仅发现模式完成工具发现后立即退出；精确只读模式的单个客户端依次完成 initialize、initialized通知、tools/list；只有user_info/file_meta的保守inputSchema profile精确匹配才调用一次user_info，并在账号匹配后调用一次仅预期fsid的file_meta。会话总预算15秒、单次I/O至多3秒，继承原字节/请求上界与socket中断/关闭确认；DNS系统线程不可强制取消，现有调用者等待有界。scope、应用provenance或真实业务信封未知不猜；业务解码仅支持现有单JSON文本候选profile，不从自然语言或errno/data猜成功。

即使uk/原文件字段都匹配，结果仍是候选匹配，**share_eligible/delivery_eligible为false**，应用权限、业务信封来源及分享对象映射不自证。不存在 `--share` 参数，不因输入token开放真实分享，也不创建/修改Job状态。原Job锁、fsync持久单次意图、未知创建不重发接口保持不变；现有接口只允许合成transport创建，未来真实分享接线须在具体权限/映射证据充分及用户相应操作后独立审查，不能用新入口绕过。

取消/异常/超时均脱敏退出，关闭客户端并释放token引用；关闭未确认返回manual_review。输入期间临时关闭自身TTY的回显、规范模式、信号字符及软件流控，退出时清除未消费输入并恢复原设置与进程signal handlers；只操作当前自有TTY，不改系统设置。不可承诺强制SIGKILL/终端故障时恢复、内存安全擦除，Python字符串/复制及操作系统层面超出该保证。

## 本轮证据

已先审阅测试数据流：父进程只向新建的自有PTY写合成token，子进程启动参数/环境无token，继承seccomp禁网，不触碰真实凭据或用户现有终端。实际PTY检查无回显、完整两次提示、取消/EOF/超时/SIGTERM/控制字符拒绝及原termios恢复；检查子进程argv/env、无后续子进程、输出/指定持久目录不泄漏。使用合成wire检查schema先于账号/单文件、空schema停止、异常不输出秘密、关闭不确认不报完成。真实分享门仍关。

干净副本 **新增23项 + 相关绑定/持久单次意图回归17项 = 40项通过，零失败/跳过**。相关回归包含未知创建后新进程不重发；没有重跑全部旧测试或把合成响应写成实网成果。没有安装依赖或改变宿主安全设置。

```sh
env -i PATH=/usr/bin:/bin /usr/bin/python3 -I -S -B tests/support/run_workflow_isolated.py test_mcp_terminal test_mcp_binding
```

[测试摘要与源码哈希](validation/mcp-terminal-2026-11-10.json)、[完整输出](validation/mcp-terminal-2026-11-10.txt)。扩展仅发现模式测试初轮有1项失败：构造器测试替身同时替换了类型检查引用，导致安全类型门拒绝测试构造；已将原类型检查与测试构造区分，保持拒绝规则后最终40项通过。[初轮输出](validation/mcp-terminal-expanded-initial-2026-11-10.txt)保留，不覆盖失败历史。

当前交付是可审阅的本地入口代码；原服务器运行、用户真实输入、授权有效性、实际schema/账号/原对象和分享均未在本轮验证。
