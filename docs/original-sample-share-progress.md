# 原样例分享推进：对象核对通过，当前 VPS 到 MCP 的直连阻断

2026-11-10，按用户“持续跟进，直到生成分享链接或者确认无法生成”的指示，继续使用原业务海外VPS、原Xtransfer授权和历史唯一NCBI样例。**原账号哈希、当前精确原文件及转换后的摘要已匹配；本轮未生成链接，具体阻碍是该VPS到官方MCP的TCP连接失败。** 未获得MCP认证/工具/分享权限结果，不称账号无权限、服务下线或永久不可分享。

## 本轮已完成

- `mcp_binding.ExpectedObject.account`支持显式`sha256:`前缀，在同机将服务返回身份转换为SHA256进行常量时间比较，兼容既有数字账号模式；不反解哈希、不用本次身份自填预期值。
- `original_sample.load_original`只读五份已明确定位的原任务记录，核对任务、目标、账号哈希、最终文件ID、目录、源/历史回读摘要、恢复与批准记录，在内存派生任务mapping摘要。这个摘要是现在构造的关联值，不伪称历史已有MCP票据或独立签名。
- 在原业务VPS原地读取原授权的首个access_token字段，经既有固定HTTPS客户端进行一次uinfo与一次唯一fs_id的filemetas；账号匹配。文件ID/path/size/类型匹配，原始md5表示不匹配，因此未继续分享。
- 一次额外精确元数据诊断确认md5字段存在但非普通十六进制。按BaiduPCS-Go固定源码`DecryptMD5`实现保守表示转换，合成测试后再查一次同一原文件：**转换后MD5与已验收源摘要匹配**。未重传、下载内容或重复完整回读；当前SHA256仍来自历史完整回读，不声称网盘本次返回SHA256。
- 最终54项禁网测试通过、零失败/跳过，覆盖哈希账号、跨记录漂移、私有文件/重复键/符号链接拒绝、错误账号阻止对象请求、对象字段漂移、混淆MD5向量与原生/MCP候选元数据集成、关闭失败及受影响绑定/终端回归。它们与以下实网证据分开记录。

转换参考：[BaiduPCS-Go固定版本util.go](https://github.com/qjfoidnh/BaiduPCS-Go/blob/1b9131817aaf8ca7dee24bc00e33ebc4c7a5cc73/baidupcs/util.go)。保留Apache-2.0许可证及来源说明；该转换不是官方权限证明，也不是新的内容读取。

## 实际 MCP 阻碍与计数

原令牌的原生网盘用途已由同机匹配账号与精确对象确认。官方[MCP README](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)给出开放平台OAuth access_token及固定`https://mcp-pan.baidu.com/sse`认证方式；本轮重新读取的README blob仍为`aebcff89265d8948be9e6dc7147cc2998b4e5d61`。企业与个人体验说明不等同于该旧应用已获MCP权限；只有实际服务响应才能进一步判断。

23:28（UTC+8）原业务VPS以既有受审官方driver尝试一次带原令牌的只读发现。DNS成功，TCP连接3秒超时，TLS及HTTP发送均未开始，故**令牌虽在同机内存加载，但未提交MCP服务**。客户端已关闭。没有收到HTTP错误/百度业务拒绝，不能据此判令牌无效或权限不足。

为了排除过短超时及首地址问题，后续不读取/携带任何凭据：

| 检查 | 实际结果 |
| --- | --- |
| 固定官方driver，I/O上限10秒、总预算15秒 | DNS成功，TCP约10.01秒超时，无TLS/HTTP，连接关闭 |
| 系统DNS当前结果 | 两个唯一公网IPv4、一个公网IPv6；未混入非公网地址 |
| 两个IPv4地址逐一进行独立网络诊断 | 各一次TCP连接，约7.01秒超时，无TLS/HTTP |
| IPv6地址一次网络诊断 | TCP未建立，操作系统网络错误；未进一步读取路由或推定具体errno |

本推进阶段合计：原生账号请求1次（为与新取得旧哈希比较，非无目的重复）、精确原文件元数据请求3次（初核、字段诊断、转换验证），均HTTP200/errno=0；MCP连接尝试2次，HTTP请求实际发送0次，initialize/tools-list/账号/文件/分享调用均0。额外3个DNS地址的网络探测无HTTP、无凭据。所有连接关闭，无代理、重定向或自动重试，无刷新/新授权/扩权、云端文件变更或分享意图消耗。

本轮代码以stdin在VPS进程内加载，未永久部署或把凭据/原始JSON/用户资料/精确ID/私有路径/会话值传回开发机、聊天、argv、环境变量或客户端日志。固定目标、公网地址与TLS主机名/证书校验保留；没有进入已拒网页、换服务、使用Cookie、借用其他应用或绕过明确拒绝。

## 可作出的结论与断点

**当前VPS直接访问该官方MCP端点的方案，本次无法推进到生成分享链接；证据是覆盖当前DNS地址的TCP失败，而不是本地默认门或官方权限拒绝。** 本轮没有可交付链接，分享结果不明/重复创建问题未发生，因为创建请求为0。

若恢复该VPS到同一官方MCP域名443的可用连接，再用原记录重建内存期望并继续：真实schema及业务信封→账号/精确原对象MCP匹配→分享资格及返回结果与对象关联→真实持久单次意图接线与一次创建。现有分享候选仍为合成实现，真实接线尚未做，原因是服务发现尚未可达；不把它描述成百度不可分享，也不在前置依赖不成立时开放写入。无需重新上传或新OAuth。代理/其他出口尚未使用，若改走其路径必须明确凭据实际流向与信任边界。

## 脱敏证据

[原生账号与首次对象核对](validation/original-sample-native-binding-2026-11-10.json)、[字段诊断](validation/original-sample-metadata-diagnostic-2026-11-10.json)、[摘要转换成功及MCP首次连接](validation/original-sample-normalized-mcp-2026-11-10.json)、[10秒无凭据连接](validation/business-vps-mcp-open-10sec-2026-11-10.json)、[DNS构成](validation/business-vps-mcp-dns-shape-2026-11-10.json)、[逐地址网络诊断](validation/business-vps-mcp-addresses-2026-11-10.json)、[测试摘要与区分的执行/最终源码哈希](validation/original-sample-binding-tests-2026-11-10.json)、[测试输出](validation/original-sample-binding-tests-2026-11-10.txt)。


后续完成无凭据路由/本机过滤清单及官方原生REST/Go SDK只读复核：未定位上游故障，REST资格未确认，不将MCP网络失败推广到全部官方路径。[替代路径证据与具体下一步](sharing-alternatives-readonly.md)。
