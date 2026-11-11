# 复用官方SDK的请求编码适配

2026-11-11。本轮完成真实官方Go SDK代码的请求生成接入，不只是兼容性样例；**通用Task上传执行器、持久上传恢复接线和VPS部署仍未完成**，不把这一步称为完成上传或整个MVP。

## 边界与输入输出

`integrations/baidu-sdk-go/codec`调用固定SDK的Mkdir、Precreate、SliceUpload、CreateFile。它使用仅捕获请求并返回固定哨兵错误的RoundTripper，从不连接百度或解析真实服务端响应，不引入scene层重试。

`cmd/ft-sdk-codec`从stdin接收至多64KiB JSON：操作、目标、大小/分片摘要、uploadid、上传域名等。分片内容由父进程传入一个只含单片的密封memfd，最多32MiB；不传文件路径、OAuth令牌、BDUSS、Cookie或密码。uploadid仅在同机私有进程间作为会话元数据使用，不跨机器或写入公开日志。输出为有上限的JSON请求信封（方法、URL、参数、Content-Type、base64请求体），不是上传成功回执。

`fast_transfer.sdk_codec.SDKRequestEncoder`核对本人所有且不可被组/其他人写入的helper/guard文件及SHA256；在空环境、关闭core dump的子进程启动guard，guard在exec前设置seccomp禁网并探测socket确实返回EPERM。哈希校验与网络限制不等于完整文件系统沙箱或安全内存擦除。父进程采用非阻塞双向管道、输出上限和25秒默认watchdog，失败只返回固定错误码。

父进程检查生成的URL/参数/任务目标、严格表单键值，以及multipart中实际单片字节完全一致，才能交给既有HTTPRequest/HTTPS通道。HTTPRequest只新增接受Go标准multipart的60位十六进制boundary，其他方法、域名、授权参数、体积和路径检查保持。BaiduProtocol的可选request_encoder只替换写请求生成，继续使用原有严格响应检查、分片MD5核对和元数据/流式回读。默认写入限制保持关闭；GET+form不能被编码器变成POST。

## 内存与空间

SDK内部会先缓冲整个multipart分片；本适配还产生捕获、JSON/base64、Python解码和memfd等副本。准入保守估算为`16 * 实际分片字节数 + 128MiB`，此外预留128MiB内存余量，核对Linux MemAvailable及可见cgroup根memory.max/current。Go GOMEMLIMIT=192MiB是软目标，不是进程RSS硬上限。嵌套cgroup或并发外部进程仍可能带来未计入压力；实际VPS峰值/取消实验待联调，不能把该估算称为已测资源SLO。

无整文件临时副本；memfd消耗内存而不是持久磁盘缓存。32MiB最大单片已通过实际SDK子进程编码往返测试，不证明百度账号允许该分片大小。后续任务执行器必须按账号探测限制选片，并在读取源文件/启动子进程之前做整个任务预算，不能只依赖这个局部检查。

## 构建与验证

固定依赖及go.sum沿用`integrations/baidu-sdk-go`（SDK要求Go1.26.2；本次Go1.27.3）。先按已有说明获取并核验一次公开依赖，然后可完全禁网构建。下面为仓库内测试输出路径，真实部署须选择新的私有安装目录，不覆盖未知文件：

```sh
# 在 integrations/baidu-sdk-go 内，用已有 Go 1.26.2+ 工具链和已准备的模块缓存
GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local CGO_ENABLED=0 \
  go build -mod=readonly -o ../../scratch/official-sdk-reuse-20261111/ft-sdk-codec ./cmd/ft-sdk-codec
chmod 500 ../../scratch/official-sdk-reuse-20261111/ft-sdk-codec
GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go test -mod=readonly ./...
GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go vet -mod=readonly ./...
```

生成guard私有副本时权限设为0600，并记录helper和guard SHA256供父进程构造器使用；不要把可由其他人写入的共享构建文件作为运行产物。对外分发二进制时保留SDK的Apache-2.0许可证与相关声明。

仓库根目录的集成检查：

```sh
python3 -I -S -B tests/support/run_workflow_isolated.py \
  test_sdk_codec test_baidu_protocol test_upload_stage test_stop_boundaries \
  test_task test_approved_sample test_isolated_candidate test_original_sample
```

helper必须先实际编译；若缺失，SDK专项类会明确跳过，不应把跳过计作验证通过。本次有实际产物，Go测试11项（5项原兼容性+6项codec）和vet通过；Python新增14项及相关回归108项共122项通过，零跳过。包含四种SDK写请求和既有协议完整模拟流、32MiB单片、hash/目标错误、网络禁用跨exec、进程超时、输出上限、内存不足和旧真实写入限制保持关闭。所有账户/传输测试使用合成数据，没有使用真实凭据或发百度请求。

## 下一步接线

将编码器接入同一Task事务/操作意图：预上传会话及确认片持久化、已确认提交不再创建、未知结果只读核查后人工接续；再接资源监测、核验完成后逐文件清理及私有交付单。继续使用Python既有HTTP策略，不让编码器成为第二套有凭据的网络客户端。真实上传命令尚未暴露，不能用原单次样例入口替代通用Task验收。
