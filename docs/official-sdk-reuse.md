# 官方API上传与Go SDK复用边界

2026-11-11。用户同意沿已验证的官方API上传方向推进，同时要求复用官方SDK以减少维护。当前确定：VPS上传继续官方开放平台OAuth/API路线；境内BaiduPCS-Go原生建链已有本人验收成功；OpenList+rclone保留备选。不因境内原生成功就把尚未验证的VPS Cookie登录当作主上传方案。

## 已落实的第一步

新增独立`integrations/baidu-sdk-go`模块，直接依赖官方Go SDK，而非复制一套请求构造代码。固定提交`472e4a1b111eac1d6307e38802f8fe7adf7e8c21`及go.sum；通过公共Go模块代理与校验数据库获取固定依赖，然后恢复子进程seccomp禁网，在独立HOME/缓存执行五项合成HTTP兼容性测试和go vet。没有接真实账号、读取凭据、创建远端对象、部署到VPS或替换现有Python上传实现。

当前模块是兼容性验证工程，**尚不是生产上传适配器**。SDK go.mod实际要求Go1.26.2，本次用已有Go1.27.3；不能只按README的1.24+说明选工具链。

| 责任 | 复用或保留方式 |
| --- | --- |
| API参数与响应结构、预上传/分片/合并编码、multipart封装 | 优先复用SDK api层，固定版本并验证升级差异 |
| 上传调度、上传会话与已确认分片持久记录、跨进程续传 | 项目保留；SDK可接收既有uploadid不等于自动持久化或服务端续传验收 |
| 磁盘/内存预算、并发和分片上限、取消与截止时间 | 项目保留；包含SDK实际缓冲开销 |
| 分片MD5、本地源摘要、最终对象一致性检查 | 项目保留，不能把SDK解析成功当内容验证成功 |
| 合并结果未知、目标冲突和重复创建保护 | 项目保留；不采用scene一键上传的默认全流程重试 |
| 请求目标/TLS/重定向/响应上限/脱敏错误 | 必须接入项目HTTP策略；SDK默认错误/调试内容不直接进入公开日志 |
| 分享交付 | 当前沿用境内原生客户端，不因上传SDK存在而推定分享权限 |

## 五项验证结果

1. SDK api三步调用正确构造合成预上传、分片和创建请求，保留路径/大小/uploadid/序号/摘要绑定。
2. 底层CreateFile遇到模拟丢失响应只调用一次，不自动重试；高层scene行为不在此保证内。
3. 分片数据在HTTP传输前已被完整读入multipart缓冲，Content-Length固定。upload_slice.go注释宣称io.Pipe流式，与当前client.go实际实现不同；预算必须按实现计算，不能直接把任意长度源流交进去。
4. SDK接收返回MD5但不与源分片自动比较，项目需确认后才登记回执。
5. 可直接用已有uploadid及指定序号上传分片，无需重新预上传；只证明客户端参数接线，不证明真实服务器的会话有效期或跨进程恢复。

## 后续通过现有Issues跟进

Issue #5负责SDK api上传薄适配及完整性：映射现有协议所需字段、端点选择和错误分类，加入MD5/精确对象检查，不复制SDK内部实现。Issue #4负责预算、任务状态、恢复及取消：每次只提供有界分片reader，核对SDK缓冲/并发开销，持久化uploadid和确认位图，提交未知不得盲目重发。Issue #2负责同一受控文件的真实VPS速度、空间峰值与断点实验。

现有编排是Python，不能直接import Go SDK。下一阶段先设计窄接口与生命周期/取消/错误脱敏契约，比较Go上传worker的进程协议维护成本，确认收益后才接入；不为“使用SDK”重写订单、下载插件和整个任务状态机，也不同时长期维护两套相同的上传请求代码。真正替换前必须保持既有API实现可回退，并用同样的错误/恢复场景验收。当前未新增运行时Go进程或进程间秘密传输。

依据：官方固定版本[README](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/README.md)、[底层client](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/baidudriver/api/client.go)、[上传场景](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/baidudriver/scene/upload.go)、[go.mod](https://github.com/baidu-netdisk/baidu-drive-sdk-go/blob/472e4a1b111eac1d6307e38802f8fe7adf7e8c21/go.mod)。
