# 当前环境内的官方分享替代路径：有界只读复核

2026-11-10。本轮不重复MCP连接试验，不读取/发送凭据、不改网络、不使用代理/隧道/其他出口，不请求真实分享或新授权。原账号与精确原样例匹配结论保留，无重传/重复完整回读。分享创建请求累计仍为0。

**结论：尚未证实当前环境存在可直接切换并自动建链的官方替代路径；也不能把MCP直连失败归纳成全部官方路径不可行。** 原生REST是独立候选，资格及Xtransfer现有应用可用性尚未取得证明。

## VPS非秘密网络状态（23:42 UTC+8）

仅对系统DNS当前解析的官方MCP域名地址执行内核route-get读取，不建立TCP连接：两个IPv4目标均得到单播路由、出口设备/源地址/网关存在；IPv6路由查询失败，系统全局disable_ipv6为false。不输出具体地址、网关、接口名或拓扑。正常IPv4路由不等于远端可达，IPv6查询失败不推定此前未记录的确切errno。

nftables表清单可读、表数0；iptables/ip6tables管理命令不可用，未安装工具或改设置。另只读核对内核legacy表清单：IPv4可读且无表，IPv6清单文件不存在（不冒称已读取并验证为空）。在这些已查信息中未见显式本机出站拒绝；**不扩大为所有本机网络机制均已排除，更不能据此指认供应商或百度封禁**。供应商侧ACL/防火墙及上游路径未读取、未确认，不发起购买、控制台登录、支持工单或抓包/新网络试验。

[路由与nft清单脱敏结果](validation/business-vps-mcp-local-network-state-2026-11-10.json)、[legacy清单](validation/business-vps-legacy-filter-inventory-2026-11-10.json)。

## 官方路径分开判断

| 路径 | 文档/源码支持的事实 | 对本项目的确切缺口 |
| --- | --- | --- |
| 官方原生分享REST | 11月8–9日已核读官方新分享服务文档，记录为POST `https://pan.baidu.com/apaas/1.0/share/set`；query为product=netdisk、appid、access_token，multipart正文为fsid_list/period/pwd；errno与data.link/data.short_url等结果分层 | 此记录不是本轮重新访问官网或本应用实测。历史官方指南要求企业认证及付费开通，用户曾明确未开通；没有新的开通证明、可信应用AppID/令牌绑定或现有Xtransfer可沿用确认。最新准入及报价还需官方确认，不能仅凭basic/netdisk或会员容量推断资格 |
| 官方MCP分享工具 | 固定官方README列file_sharelink_set，fsid_list是字符串ID的JSON数组字符串，period按天、默认7天，pwd四位数字/小写字母；输出link/short_url/period/pwd | 本VPS未进入TLS/HTTP，没取得实际认证、schema或业务返回。README不公开远端分享实现，不证明它内部恰好调用上述REST、共享付费资格或可等价绕过开通；个人体验条件不能推导旧Xtransfer/商业可用 |
| 当前官方Go SDK | 本轮读取baidu-netdisk官方组织下baidu-drive-sdk-go的README、未截断树和Client导出服务；服务为Auth/Nas/File/FileManager/Upload/Download，没有Share服务，树中无分享专用文件 | SDK存在不等于新增分享权限，当前已审范围没有可直接替代MCP的分享方法；未安装或执行SDK，也不把它的缺项当作原生API不存在 |
| PCS/客户端网页登录通道 | 历史BaiduPCS-Go分享走Cookie登录及share/pset | 与OAuth开放平台REST不同，不能把现有access_token直接移用；本轮不采用、不访问已拒网页、不读取Cookie或另寻网页替代入口 |

REST主机与既有uinfo/filemetas同属pan.baidu.com，已有原生读取成功说明当时该主机相关只读路径可达；**不证明apaas路径可达或服务已开通**。无须为了测试资格执行具有建链副作用的POST。原生REST不是第三方新接收方，但新接口的应用/服务资格、计费及行为仍须核对；本轮没有向它提交令牌。

REST与MCP也不能共用未经转换的响应解码：前者记录为errno/data信封，后者先有标准MCP CallToolResult，再有尚待实测的业务内容。两者列出的分享链接字段都不足以单独证成账号/原文件完整映射；真实接线仍需验证来源、唯一原对象、期限和创建结果，持久一次意图先于发送，结果未知不重发。原生接口不应采用早期不准确资料中的filemetashare、fid_list/schannel/expired_type组合。

## 依据与时效

- [既有官方REST资料核读记录](baidu-share-service.md#2026-11-09自动建链资料核对仅公开文档源码)及[11月8日官方来源URL/reader文本摘要哈希](validation/mvp-live-sample-2026-11-08.json)。本轮不重访此前被拒的网页、不用reader/代理间接重试；旧记录的付费/准入说明不伪称新控制台证明，未取得统一报价/豁免证据。
- [官方MCP固定README](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)，blob `aebcff89265d8948be9e6dc7147cc2998b4e5d61`。
- [当前官方Go SDK README](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/main/README.md)，blob `9e825aa81f35d6caeecb6f72b9b4cd1cd25dc029`；[Client服务](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/main/baidudriver/api/client.go)，blob `770dc1c1c3136db35488a89cb6d945fb906aee92`；完整树SHA `472e4a1b111eac1d6307e38802f8fe7adf7e8c21`。只读公开GitHub资料，不执行代码。[本轮来源及未执行动作摘要](validation/sharing-alternatives-readonly-2026-11-10.json)。

## 最小下一步与需用户决定之处

1. 网络路线：只读核查现有供应商控制台中该VPS出站ACL/防火墙，或由网络提供方解释到固定官方MCP端点的可达性。当前没有该控制台的已授权连接/读数，不自行登录、发工单或更改安全设置；本机已查信息不足以定位上游丢包点。
2. 原生REST路线：从现有Xtransfer应用的官方服务列表取得“文件分享服务是否开通、应用主体/对应AppID、原授权是否适用”的非秘密事实，核对当前官方资格和报价。无需重新上传、提供令牌或新OAuth。若仍未开通，是否申请企业/经营主体认证及购买服务属于具体用户决策；金额、主体及条款未知时不代办。
3. 上述任一前提取得可靠证据后，再做该路径的最小只读核对和唯一原样例单次建链；本轮研究不能替代它们。当前无经验证链接，也无官方分享接口明确权限拒绝，因此保留“本VPS MCP直连受阻、REST资格未确认”，不写成“所有官方渠道均无法生成”。
