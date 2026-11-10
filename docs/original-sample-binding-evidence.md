# 原样例身份与对象绑定：只读证据整理

2026-11-10。本轮只回查指定公开验收文档、脱敏收据及其写入代码；未读取私有收据/凭据、未扫描VPS、未访问百度或MCP、未重传或重复测试。以下是历史记录和静态接线依据，不是原对象当前存在性的实测。

## 证据及齐备程度

| 所需字段 | 已有来源及确认程度 | 当前缺口 |
| --- | --- | --- |
| 预期账号 | `mvp-live-sample.md`及脱敏JSON的`observed.identity_matched_prior_fingerprint=true`记录当时匹配成功；`approved_sample.py`私有会话写入逻辑记录账号SHA256 | 公开收据没有指纹值；未核验指定私有记录当前存在、可信性和完整字段。哈希不可反解账号ID |
| 精确云端文件 | 文档记录提交fs_id/path/类型/长度验证成功；`sample_recover.py`成功分支将最终对象ID写入原任务`recovery-result.json`的`verified_object_id`，路径沿用原结果的target | 公开收据只保留验证结果，未保留精确文件ID/完整随机路径；私有结果尚未读取。目录ID、uploadid均不能替代最终文件ID |
| 任务与目录关联 | 原结果、precommit-inspection及恢复结果代码逐项约束同job_id/target；私有会话检查点记录目录/源哈希/账号指纹 | 这是写入与检查逻辑，不证明私有记录现在齐全；MCP所需mapping摘要及原任务关联尚未装配验证 |
| 内容 | 脱敏JSON公开大小1,379,902字节、源及完整回读MD5/SHA256，并记录source_matches_readback=true | 内容历史验收齐备，无需为此再次完整回读；不证明文件当前仍存在或MCP可见 |
| 应用 | 历史应用标签Xtransfer及应用目录约束；原生uinfo单次成功另有收据 | 标签、目录或账号一致都不能证明OAuth AppID绑定、MCP兼容或分享资格 |

私有记录名仅用于说明现有代码的预期来源，不公开其绝对位置、账号指纹、原始云端标识或会话值。尚未从私有文件读取这些字段，因此不能声称“已经找到可用的可信定位输入”。`recovered-session.private.json`是预提交检查点：包含目录ID/源摘要/账号哈希等，不保证包含提交后的文件ID，不能单独满足最终对象定位。

来源：[验收文档](mvp-live-sample.md)、[脱敏历史收据](validation/mvp-live-sample-2026-11-08.json)、[恢复结果写入逻辑](../fast_transfer/sample_recover.py)、[私有检查点逻辑](../fast_transfer/approved_sample.py)、[当前绑定接口](../fast_transfer/mcp_binding.py)。

## 从现有授权到原对象分享的最小依赖（候选，未执行）

1. 由原任务的明确私有位置提供最少预期字段并在VPS内核对来源/权限/任务关联；不扫描、不导出原始标识。最终文件ID应来自提交后的恢复结果，结合原target及已验收内容。历史只有账号SHA256时，在同机对当前身份求哈希匹配；现有ExpectedObject接收原始账号ID，需适配哈希核验或由独立可信私有来源提供原始预期账号，不能反解哈希或把本次响应自填为预期值。
2. 独立确认现有Xtransfer令牌的MCP用途/应用范围及向固定官方SSE提交的数据流。原生uinfo成功只证明该原生服务当次接受令牌。固定官方README给出查询参数认证和个人独立体验OAuth，但未证明任意旧应用令牌均兼容；本轮不传令牌、不新授权、不部署。
3. 若进入获准的MCP只读阶段，先握手及tools/list取得真实inputSchema/认证与业务信封；匹配后才一次user_info及一次精确原文件file_meta，核对账号、fsid/path/size/MD5。不能因无凭据tools=[]推定带凭据必成功；不能猜参数或枚举全盘。一次精确file_meta可补当前对象存在/可见及元数据匹配缺口，但不能独自证明旧账号指纹来源或应用绑定，也不必重复完整回读。
4. 真实分享前还需核实分享资格、实际成功/拒绝信封、链接与原账号/对象的可验证关联，并将真实驱动接入已有持久单次意图流程。现有官方驱动只读；候选分享使用合成transport，不能直接用于真实创建。固定文档仅列返回link/short_url/period/pwd，未给充分owner/fsids核实契约，不能返回URL即标已验证/已交付。

固定来源：[官方MCP README（已记录版本）](https://github.com/baidu-netdisk/mcp/blob/b3983d330fea79c7b72e6b7014803e1830148d2c/README.md)。以上依据项目此前固定源码审阅，本轮没有重新联网查询或宣称平台当前能力已验证。[原生uinfo结果](validation/xtransfer-uinfo-once-2026-11-10.json)与[实际MCP绑定缺口](mcp-binding.md)分开看待。网页既有拒绝不重试，任何新的明确拒绝均停止，不绕过。
