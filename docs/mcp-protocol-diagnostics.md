# 设备兑换成功报告后的 MCP 工具发现校验失败

2026-11-10：依据用户主动提供的**脱敏终端结果**进行静态跟进。本轮未读取用户终端/进程argv或环境/内存/凭据，未新发设备码、兑换/刷新、MCP或业务请求，没有恢复token或变更原对象。本页的真实运行结果来自用户报告，不能冒称本轮代理独立实测。

## 已知、可推断与未知

| 层次 | 依据及结论 |
| --- | --- |
| 设备兑换 | 用户报告device_authorized_in_memory、scope basic netdisk、一次轮询、authorization_outcome_unknown=false；按入口逻辑说明已取得并校验内存lease，报告当时剩余2591999秒（约30天）。不是MCP已认证证明 |
| MCP初始化 | 报告sse_open/initialize/initialized/tools-list各一次。按现实现顺序，已通过初始SSE端点及initialize校验，进入tools/list请求；不能把计数当服务端工具成功回执或推断未提供的精确HTTP状态 |
| 拒绝 | mcp_sse_protocol_rejected是**本地通用协议校验码**，不是已识别的百度权限拒绝码。旧报告没有具体规则、字节数、ID匹配或分页信息，无法确认真实触发点 |
| 退出 | 用户报告close_confirmed=true、token_stored=false。原入口结束释放引用；此入口无安全恢复该token的持久记录。本轮不尝试扫描或恢复 |
| 未做的业务 | 账号/原文件未验证、分享未尝试。live_authenticated=false、application_binding_verified=false是保守未验证标志，不能解读为已证明账号/应用错误 |

据当前代码路径，初始SSE不可达/初始端点未匹配/initialize版本未通过，不是这份报告所示的**第一个**失败点；也没有设备兑换失败的报告。但仍不能排除服务在后续返回了当前客户端不能解释的认证/其他响应，更不能从通用本地错误推断官方权限拒绝或全部认证通过。

候选原因包括：16KiB事件/待完成行上限、总字节/行限制、id/retry等未审SSE字段、额外通知、RPC id/信封形状、分页、tools/list结果额外字段。工具列表较大可能触发限制，但没有历史字节数，**不是已确认根因**。JSON列表/字符串/深度限制也可能成为后续兼容边界；其独立错误码通常不同，不能拿合成复现强称就是本次原因。

## 本轮代码修正

- `SSEClient.protocol_diagnostics()`输出固定阶段/规则枚举、字节和行数、事件计数、客户端自有RPC序号、响应ID是否匹配、分页是否存在、最多6个整数HTTP状态。**不输出实际响应ID、endpoint/会话/游标、schema原文/字段名/元数据内容或原始异常**。端点、TLS、原大小/数量/时间限制、禁止跨域/跳转/重试/分享均保持。
- 终端只读及仅发现模式带回上述诊断。事件大小、EOF、SSE未知字段、RPC信封/ID、工具列表分页等现在能分别定位；旧通用reason保持兼容。
- [MCP Python SDK v1.6.0 types](https://github.com/modelcontextprotocol/python-sdk/blob/v1.6.0/src/mcp/types.py)中ListToolsResult继承PaginatedResult/Result，Result定义可选dict/null `_meta`。静态确认旧客户端会错误拒绝这一标准字段，现接受**仅dict/null**并忽略其值，未知字段及分页仍停。这是可复现的标准兼容修正，**不证明实际失败响应带了_meta，也不证明已修复官方互通**。
- 设备入口新增独立 `device_authorization_complete` 与 `mcp_discovery_complete` 标志，后者还要求发现状态完成及关闭确认；避免将旧顶层finished当作MCP成功。它仍只表示工具发现协议完成，不等于已认证/已取得业务权限，授权、token存储和调用范围不变。

## 实际检查与边界

干净副本新增诊断13项、受影响SSE17项/终端23项/设备结果标志25项，共 **78项禁网检查通过**；共享SSE解析改动另执行 **21项真实本地TCP/TLS回归通过**，零失败/跳过。合成重现超大单行/多行、EOF、通知、ID漂移、分页和额外字段的不同本地规则；验证标准_meta不会进入输出、大小上限仍在、原未知创建不重发/业务门及两阶段状态分离保持。

本轮OAuth/MCP网络为mock或明确本地fixture，不是用户那次服务器响应，不替代实网复测。没有请求或保存真实秘密，也没有部署/合并。[摘要、用户报告来源与源码哈希](validation/mcp-protocol-diagnostics-2026-11-10.json)、[禁网输出](validation/mcp-protocol-diagnostics-offline-2026-11-10.txt)、[本地TLS输出](validation/mcp-protocol-diagnostics-local-2026-11-10.txt)。

## 后续最少需要什么

当前旧报告不含新诊断，无法追补，不要求用户发送原始响应、截图、链接或token，**也不要求现在重做授权**。只凭本次结果已经能确认设备兑换和MCP校验是不同阶段，真实分享未发生。

若以后另行允许一次最小协议复测，前提是用户本人有一份获准、仍有效的token可在隐藏终端输入；当前程序未存储上次token，不能承诺恢复。没有现成token时，需要另行决定是否启动下一次设备grant，不能为抓诊断自动重做OAuth、兑换或刷新。最小复测仍仅1GET+initialize/initialized/tools-list三次POST，无账号/原文件/分享请求。

届时只需以下**脱敏字段**：`mcp.reason`、`mcp.protocol_diagnostics.stage`、`failure_rule`、`sse_bytes_read`、`event_bytes`、`pending_line_bytes`、`rpc_id_matches`、`pagination_present`、`http_statuses`。其中规则通常即可定位；不需要整个JSON、响应内容、服务器实际ID或游标。执行代码的短提交号也可作为非秘密版本依据。没有这些新观测前，不扩大大小限制、不实现未审分页/通知，也不把_meta修正宣传为根因已解决。
