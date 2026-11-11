# 版本化运行包与首次VPS检查

2026-11-11。已将`2d83444a65fa35a23c9d789d9e799eb5c9914a48`的运行代码安装到VPS独立版本目录。没有覆盖历史实验、原样例、授权文件或原生客户端；没有切换常驻服务。以下是安装与无凭据检查证据，不是新文件真实上传验收。

## 运行包

`scripts/build-mvp-release.py`只从干净的已跟踪工作树打包运行模块、公开候选manifest、guard、已构建helper和SDK许可证，不复制工作目录、实验文件、认证配置或Go缓存。helper必须事先按固定SDK集成构建/检查；打包器本身不证明任意传入二进制来源，也不联网安装依赖。

```sh
python3 -I -S -B scripts/build-mvp-release.py \
  --helper /PRIVATE/ft-sdk-codec --sdk-license /PRIVATE/SDK-LICENSE \
  --output /PRIVATE/release-new.tar.gz
```

归档49个文件，其中release.json记录48个载荷文件的SHA256/权限及源码版本；helper静态Linux amd64二进制，500，其余600，SDK Apache-2.0许可证与上游提交说明随包保留。归档SHA256是本次构建产物身份，不是签名或可重复构建保证。

安装至新的本人0700版本目录，独占创建，不覆盖现有版本。安装前核对归档摘要，拒绝链接/非普通文件、重复成员、绝对路径与父目录跳转；逐文件核对摘要、权限、所有权，并编译检查Python语法。实际安装已完成这些检查。

## 使用

在实际私有安装目录，通过隔离Python入口调用，不依赖工作目录、PYTHONPATH或用户site配置：

```sh
/usr/bin/python3 -I -S -B /PRIVATE/RELEASE/launcher.py task --help
/usr/bin/python3 -I -S -B /PRIVATE/RELEASE/launcher.py task_upload --help
```

其余命令为task_handoff、task_cleanup、delivery、task_delivery、intake，具体参数见各说明。launcher设置umask077和禁用core dump，命令白名单；仍不等于完整文件系统沙箱。helper/guard继续逐次按运行包记录的摘要核验，Go编码进程禁网。实际账号操作仍需显式任务/账号/对象范围。

## VPS实际检查

- x86-64、Python3.13.5、libseccomp.so.2存在；检查时可用磁盘24,323,592,192字节。
- 48个载荷文件摘要/权限/所有权及Python语法通过，7个CLI帮助入口通过。
- 实际guard+helper生成目录请求和4MiB单片请求，单片字节核对通过；未发送这些请求。一次编码检查耗时0.3588秒，父进程峰值RSS48,512KiB，helper子进程峰值RSS29,244KiB。
- RSS为该次编码检查的进程级ru_maxrss，不能作为完整下载/上传任务峰值、进程合计峰值或性能承诺。真实HTTPS、源落盘、账号资格、读回和故障资源联合验收仍待做。
- 已建立一个独立公开蛋白FASTA候选任务，单文件上限1MiB、阶段pending；未下载载荷，未读取凭据、发百度请求或建云端对象。任务ID、具体安装/状态/认证路径只留私有操作记录。

准备命令的一次SSH连接关闭，随后只读确认未产生准备记录；改用任务锁与已有任务核对后完成准备，没有盲目重复上传或账号操作。现有任务保持pending，等待新文件明确范围。分享/领取由本人原生客户端执行，不由部署过程自动触发。

## 下一项待确认范围

候选`GCF_000005845.2_ASM584v2_protein.faa.gz`为902,395字节，官方MD5已随示例记录。已向本人请求一次该新文件的源下载、原地OAuth账号/容量核查、新独立Xtransfer对象上传/完整回读、本任务元数据交接及核验后本地载荷清理范围；尚未获得答复时不得执行相关账号动作。分享与未登录领取继续由本人操作。
