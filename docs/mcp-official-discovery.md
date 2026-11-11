# 正式客户端官方路由与无凭据工具发现

2026-11-10：正式 `OfficialHTTPSDriver` 与 `SSEClient`/`BoundSession` 已接入实测profile：**同HTTPS主机 `/message` + 单个 `sessionId` 查询参数**。只允许精确静态路径和受限会话字符/长度；跨域、userinfo、其他端口、额外查询、百分号、fragment、尾斜杠及旧profile混用在发包前拒绝。合成/本地测试继续使用独立 `/messages` + `session_id` profile，不把任意URL变成可用路由。

`OfficialHTTPSDriver(access_token=None)` 可进行无凭据协议发现，GET路径严格为 `/sse`，不发送虚构或空令牌、不读配置/环境/浏览器。此时底层直接拒绝所有 tools/call；显式传入短期token的既有路径仍只允许 user_info/file_meta，分享继续拒绝。`OfficialDiscoverySession` 只接受无凭据的精确官方driver，只能 initialize、initialized通知和tools/list，工具调用及其他RPC在发包前拒绝；不会因为发现成功自动检查账号或文件。TLS/域名校验、公共地址/DNS固定、deadline/socket关闭、无代理/重定向/重试与脱敏不变。

## 真实官方观测

2026-11-10 **17:43:57（UTC+8）**，当前项目执行主机直接使用上述正式模块（不是独立协议探针、不是海外VPS）：

| 项目 | 实际结果 |
| --- | --- |
| 请求 | 1GET `/sse`、1initialize POST、1initialized通知POST、1tools/list POST |
| HTTP | 顺序为200、202、202、202 |
| TLS | TLS1.2，证书链及官方主机名校验通过 |
| MCP | initialize及tools/list响应通过现有严格JSON-RPC校验 |
| 工具发现 | **tools=[]，工具数0**；未得到user_info、file_meta或分享工具schema |
| 用量/退出 | 读383字节SSE，约0.957秒，关闭确认；没有重试/跳转 |
| 认证/业务 | 无凭据，用户/原文件/分享调用均0，未做OAuth或账户动作 |

事实是“该无凭据会话返回空工具列表”。可能与未认证、应用权限或服务配置有关，但本次没有明确认证错误，**不能断言缺少token是唯一原因，不能称账号已认证或账户无权限**。schema读取流程成功不等于已取得具体工具schema。当前不能继续账号/精确文件校验，也不应向未知工具猜参数。

## 凭据与原对象的精确缺口

已复核公开的历史样例记录：原获准范围是现有Xtransfer access_token临时内存使用、精确NCBI样例完整性成功后的受控建链，不包括新OAuth/刷新/Cookie/应用密钥、其他文件或接收人。未读取私有配置或原收据。历史上传成功不证明现有token未过期、兼容MCP或当前应用有相应权限。

继续只读核验需要明确以下**具体方案**，不是再次询问是否想分享：

- **来源/主机**：允许从原测试VPS上既有、明确指定的OAuth存储读取短期access_token；建议在原VPS的同一受审进程内使用，避免把token转到当前项目主机。不得搜索其他配置/环境/浏览器，不导出或使用refresh token、Cookie、应用密钥；若存储同时含其他秘密，需要审阅字段读取实现，不能把“只用access_token”说成已隔离其他内容。
- **目的地/风险**：该token仅经TLS提交官方 `https://mcp-pan.baidu.com/sse` 的查询参数认证；不进入argv、日志、公开文件或LLM。官方服务/中间设施可能记录URL，客户端脱敏无法控制其日志。现有上传权限不能替代对这一MCP数据流及兼容应用的核实。
- **范围**：先发现schema及其认证要求；确有匹配工具和权限后，最多一次user_info和一次原精确fsid的file_meta，只与原私有收据的账号/应用/路径/长度/哈希比对，不枚举全盘、不迁移/重传。凭据过期、不兼容或遇新拒绝即停止，不刷新或另建授权。此次尚不执行分享。

上述读取来源、执行位置、MCP提交范围和兼容性证据未补齐，本轮没有实施。原文件ID/账号/路径仍应从可信私有任务收据取得并内存传入ExpectedObject，不发布这些标识，不把候选输入当权限证明。

## 分离的代码检查

干净副本：新增路由/发现9项 + 受影响官方driver13项 + 绑定17项 + SSE17项，共 **56项禁网检查通过**；另因共享HTTP/profile改动执行 **21项真实本地TCP/TLS回归通过**，均零失败/跳过。这些测试与上面的正式官方实测单独记录；没有把mock或本地TLS称为认证/业务成功，没有重跑全部旧测试替代进展。

[官方实测及已执行源码哈希](validation/mcp-official-discovery-live-2026-11-10.json)、[执行入口](validation/mcp-official-discovery-probe-2026-11-10.py)、[测试摘要](validation/mcp-official-profile-tests-2026-11-10.json)。后续源码仅补充docstring，执行哈希保持原样，未用新文本覆盖实际运行证据。

后续：[原授权非秘密元数据核查](xtransfer-auth-metadata.md)已完成；指定位置存在，但当前实际scope/到期时间/应用绑定仍未知，未读取或发送令牌。

新增[服务器终端本人无回显输入入口](mcp-terminal.md)，本轮仅无凭据开发及合成验证，未启动OAuth/读真实token或访问服务；不因人工输入放开分享门。

后续用户执行报告与静态跟进：[设备兑换返回成功、MCP tools/list本地校验失败](mcp-protocol-diagnostics.md)。已补诊断及标准_meta兼容，根因和官方互通尚未实测确认，本轮没有新授权或读取秘密。
