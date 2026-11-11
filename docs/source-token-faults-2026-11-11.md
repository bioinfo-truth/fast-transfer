# 源中断、无效令牌与空间准入：真实故障验证

2026-11-11。在已交付鼠任务之外建立两个隔离的**源阶段本地测试任务**，只下载同一NCBI公开GRCm39报告（7,187字节）。没有云端上传/创建对象，不用于绕过已交付任务；原任务SQLite摘要前后相同。测试目录、PID/启动时间、源片段和全部结果保留在私有工作区。

## 真实源下载中断

调用已安装4c8ea43的Task和download_verified，使用真实public HTTPS响应。为确定性暂停，部分下载场景只将read1每次读取上限设为1,024字节；没有伪造响应或文件内容。父进程收到READY并确认子进程存活后发送SIGKILL，wait确认退出，再由新Task实例重开原状态。

- **不完整源**：downloading状态与1,024字节部分文件保留。recover-source因source_size_mismatch拒绝，不发起网络；保存一份部分源证据后，通过既有reset_incomplete_source显式重启。只删除这个新测试任务的已知部分载荷，原片段副本保留；再次真实下载7,187字节，MD5与官方manifest匹配、SHA256核验成功，source_verified、云端操作0。
- **完整源落盘、Task收据未写入**：实际download_verified成功后在返回Task前暂停，SIGKILL后完整7,187字节仍在、状态downloading。新实例recover-source独立重哈希并保存源收据，network_repeated=false，不再次下载，云端操作0。

两种场景SHA256均为`e3fb259bf1d1ee3b646c1f697a39c8394a6342d790fca9c1b36a8c873063ae26`，MD5为`1fd6ffdf5da458e9d4f4e5b82d482601`。这是实际HTTPS与进程强杀恢复，不是自然上游断网/断电，也不是HTTP Range字节续传；不完整源明确从头重启。

## 无效令牌拒绝与原账号复检

使用同一已验证鼠对象的精确scope和原账号摘要，客户端强制read_only。第一阶段provider只返回一个明确无效的测试字符串，不读取/改写真实认证文件；实际GET uinfo得到HTTP200、errno=20017，协议以protocol_api_error停止，没有后续quota或POST。客户端停止、内存引用释放。

第二阶段在原位置延迟读取现有access_token，仅GET uinfo/quota；两者errno=0，账号摘要匹配。原凭据文件inode/大小/mtime/ctime前后不变，未刷新或撤销令牌、未登录，未跨机传凭据。保存的是安全错误码与固定布尔结果，没有记录令牌或服务响应原文。

该试验验证**无效测试令牌**的实际服务拒绝和闭合失败，不宣称自然到期、真实expired-token错误码或刷新机制已经通过；本MVP不自动刷新凭据。

## 真实可用空间低于底线

使用已有容量受限临时文件系统，新建空的本人私有测试目录，实际可用1,034,870,784字节，小于5GiB（5,368,709,120字节）底线；没有mock statvfs或填满全机磁盘。Task.create在preflight_workspace即以space_workspace_reserve拒绝，未创建Task。直接download_verified的准入也以disk_budget_exceeded拒绝，网络入口计数0、未创建载荷或云端操作。原试验计划在Task创建后观察下载失败，实际证据是更早一层已经拒绝，不能虚构source_failed任务。测试目录及安全摘要保留，没有触碰原任务。

这证明实际低可用空间的**准入拒绝**，不是下载途中突发ENOSPC、全机磁盘填满、OOM或硬内存限额验收。

## 后续门槛

本轮补上实际源阶段SIGKILL/重开，以及实际服务无效令牌拒绝证据。现有鼠任务已实测分片未知的一次有限重试与读取失败后的GET-only恢复；未知commit只读核查仍有合成/实际本地exec测试，缺新实网故障证据。运行途中空间突降/配额边界及整体操作手册核对仍需推进，不因本轮两个只读验证就宣布完整MVP完成。

机器记录见[source-token-faults-2026-11-11.json](validation/source-token-faults-2026-11-11.json)。测试worker通过私有日志定位，原始目录/PID/任务ID不发布；保留源和收据，未清理原已交付样例或发起新分享。
