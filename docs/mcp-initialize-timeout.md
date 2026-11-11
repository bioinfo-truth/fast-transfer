# 第二次报告：initialize POST 本地超时

用户第二次脱敏报告显示设备兑换完成、scope basic netdisk、6次设备轮询；MCP只读到81字节/1个endpoint事件，initialize提交计数1、initialized/tools-list为0、HTTP状态仅[200]，close_confirmed=true。本轮未读取秘密、重授权/兑换/刷新或发官方请求。该报告没有主机/出口/代码版本，**不能断言来自业务VPS**，最新业务目标见[前置核查](business-vps-preflight.md)。

## 可确定解释

- 按报告及当前代码，GET响应与endpoint事件已处理，客户端进入initialize POST；唯一200对应此前GET，**不是initialize响应**。initialize计数在连接和发送之前增加，不能当作服务器已收到或确认请求。
- POST每次新建固定目标TCP/TLS连接，初始GET成功不证明第二条连接成功。旧initialize_post阶段涵盖TCP、TLS、发送和等待响应头；没有这些子阶段信息，无法确认这次实际超时点，更不能叫官方权限拒绝。
- 按54977f4实现，设备结束/用户确认MCP-DISCOVER后才新建MCP驱动与会话，独立15秒总预算、3秒I/O上限；**不沿用六次设备轮询起点**。报告未标版本，不能把静态证明当作现场版本核验。
- 旧pending_line_bytes在每次读入时保存峰值，未在解析行后归零。81不是“尚未消费”；event_count=1说明事件已解析返回。它也不是本次SSE等待数据超时，报告阶段仍在POST。
- 新报告尚未走到tools/list，所以没有实际检验上一轮_meta兼容修正，不能把新超时当该修正失败或成功。
- mcp_local_*是共享模块遗留错误前缀，**不说明程序在开发机/localhost**，更不能据此确定网络出口。

## 已修的可证实客户端问题

新增固定字段的transport诊断：operation、TCP/TLS/send/response_headers/SSE-read阶段、客户端连接序号、分段耗时/是否完成、独立会话耗时/预算/剩余时间、单次I/O参数、DNS次数、最近request发送调用是否返回与响应头是否收到、最多32条安全历史。没有地址/URL/会话/令牌/实际响应或原始异常。发送调用返回也不等于服务器确认。

显式一次connect后禁用http.client自动open，TCP/TLS完成后分别在发送和响应头前按**同一绝对deadline**重新设置socket timeout；总预算和I/O上限不增加，不自动重试、不换节点或代理。另修复watchdog线程标志尚未更新时，只看_expired可能把已过绝对deadline的Timeout误标I/O timeout；现同时看monotonic时钟。这是可复现的分类问题，不证明就是历史报告根因。

SSE诊断将pending_line_bytes修为当前未完成行缓冲、buffered_bytes为尚未消费缓冲，line_buffer_high_water_bytes另存峰值；event_bytes继续表示最近事件大小，不代表未消费。响应上限及所有业务/分享门保持。

## 本地复现与证明范围

- 真正本地TLS的第二条连接握手停滞，可复现initialize_post、仅GET200、零初始化HTTP正文到达服务端；新诊断定位tls_handshake。
- 真正本地TLS的POST已读但响应头停滞，也可复现相同旧表象；新诊断定位response_headers、send_returned=true/headers_received=false。因此旧报告无法二选一。
- 真正本地TLS读到正好81字节endpoint并完整消费，新计数event_count=1、buffered/pending=0、high_water=81，证明旧计数语义问题。
- 合成注入分别覆盖TCP/发送/响应头超时、每阶段socket timeout刷新、总deadline不延长、watchdog标志延迟分类与新会话独立预算；不触碰官方服务。

干净副本新增7项transport检查及100项受影响协议/终端/设备回归共 **107项禁网通过**；原21项本地TLS加3个新情形共 **24项本地TLS通过**，零失败/跳过。它们不是官方网络根因确认或业务VPS验收；VPS只做了不落盘源码compile/依赖和文件metadata预检。

目前不要求第三次授权，也不能恢复上次未保存token。正确下一步是先确认业务VPS代码/无凭据链路；若以后另行允许仅协议复测，所需脱敏字段为transport.phase/phase_elapsed_ms、session_elapsed_ms/remaining_ms、last_request_send_returned、last_response_headers_received、http_statuses、buffered_bytes/line_buffer_high_water_bytes及节点角色/代码版本。不需要秘密、截图或原始滚动输出。[测试与报告来源收据](validation/mcp-transport-stages-2026-11-10.json)。
