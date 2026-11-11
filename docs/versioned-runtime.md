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

候选`GCF_000005845.2_ASM584v2_protein.faa.gz`为902,395字节，官方MD5已随示例记录。此前已请求单文件范围；后续用户明确要求沿用既有令牌继续推进，现已完成该新任务上传/完整回读及本地清理、境内原生分享，本人已明确反馈提取并下载成功，确认收据已关联。无需再提供账号密码，详见`docs/protein-pilot-2026-11-11.md`。


后续63a9840版本已独立安装并核对，包含通用资源采样；没有改变原候选任务或执行账号操作。50归档文件/49载荷通过核验，具体采样数据与完整MVP缺口见[验收状态](mvp-acceptance-status.md)。2d83444继续保留作历史检查依据，不覆盖版本文件。


后续暂停功能运行包2772a7a已独立安装VPS：51个归档文件、50个载荷的摘要/权限/所有权及Python语法核对通过；补齐引用的BaiduPCS-Go许可证。7个CLI帮助入口和SIGUSR1置位/原处理器恢复检查在内核禁网下通过。保留旧63a9840版本，未启动服务、读取凭据或执行上传；现存48号片未知不变。安装和离线信号检查不等于实网分片恢复，证据见`docs/validation/pause-runtime-deployment-2026-11-11.json`。

## 2026-11-11：稳定性运行包本地准备完成

已从干净已跟踪版本a6c75a1697fff73ce40e0ca53dfeb22bdd41b6aa构建本地运行包；归档SHA256为 `0bd3a5fbfcefb4a2b6e2c4a6682c6b52ea2b9962e5f4d0c52fd05ea2d48cc2aa`。52个普通成员、51个载荷的名称/摘要/权限/所有权和Python语法通过。使用临时HOME、继承性内核禁网运行解包后7个CLI帮助，确认readback-only选项；通用合成manifest创建和show返回恢复建议且数据库字节不变，非法命令拒绝。

这是本地运行包冒烟检查，不是打包后完整上传验收或VPS部署证明。没有读取凭据、下载真实源、上传或分享。具体证据见仓库 `docs/validation/stability-release-local-2026-11-11.json`。

待确认的具体范围：将该包安装至既有VPS新独立目录，保留旧版、不切换服务，仅做无凭据禁网入口检查；另行确认是否允许同步GitHub/Wiki。已向本人提出选择，回复前不执行这些受既有明确限制的动作。安装代码归档不包含任何数据载荷、账户配置或私有任务收据，不改变此前受阻来源/操作限制。
