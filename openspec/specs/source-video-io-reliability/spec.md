# source-video-io-reliability Specification

## Purpose
TBD - created by archiving change harden-project-reliability-and-delivery. Update Purpose after archive.
## Requirements
### Requirement: 源视频 MIME 与文件资源释放

视频流 SHALL 保留既有播放版优先级，根据最终文件确定 MIME，所有支持上传的后缀 SHALL 不因类型变量未初始化产生 500；不得承诺浏览器支持所有容器中的编码。

#### Scenario: 非 MP4 源文件
- **WHEN** 请求已登记的 MOV、WebM、M4V、AVI 或 MKV 文件
- **THEN** 系统 SHALL 返回正确的容器 MIME 和文件 bytes，普通 GET 为 200

#### Scenario: 文件缺失与连接中断
- **WHEN** 文件缺失或客户端提前停止读取
- **THEN** 缺失文件 SHALL 返回 404，已打开句柄 SHALL 在迭代退出后关闭

### Requirement: 单范围和 HEAD 协议

系统 MUST 正确处理单一闭区间、开放区间及后缀 Range，响应头必须与实际 bytes 一致，并支持无响应体 HEAD。

#### Scenario: 请求末尾字节
- **WHEN** 对内容为 `0123456789` 的 10 字节文件请求 `Range: bytes=-3`
- **THEN** 系统 SHALL 返回 206、`Content-Range: bytes 7-9/10`、长度 3 和内容 `789`

#### Scenario: 开放与超长后缀范围
- **WHEN** 对 10 字节文件分别请求 `bytes=4-` 或 `bytes=-20`
- **THEN** 系统 SHALL 分别返回字节 4–9 或 0–9，状态均为 206，长度与 Content-Range 一致

#### Scenario: 不可满足范围
- **WHEN** 起始位置超出文件、后缀长度为零或空文件收到 Range
- **THEN** 系统 SHALL 返回 416 和 `Content-Range: bytes */<size>`

#### Scenario: 非法或多范围请求
- **WHEN** Range 单位或语法非法，或请求多个合法范围
- **THEN** 非法输入 SHALL 返回 400；合法多范围 SHALL 忽略 Range 返回完整 200，不返回错误拼接的 206

#### Scenario: HEAD 请求
- **WHEN** 客户端发起 HEAD
- **THEN** 系统 SHALL 返回对应 GET 的状态和实体响应头，不打开正文流或发送响应体

### Requirement: 有界上传和失败清理

系统 SHALL 提供正整数 `PICKLEBALL_MAX_UPLOAD_BYTES`，默认 20 GiB，以实际文件累计大小限制上传，入站 multipart 总量 SHALL 额外仅允许 1 MiB 开销。失败上传 MUST 不进入素材目录。

#### Scenario: 无声明长度的超限上传
- **WHEN** 无 Content-Length 的请求实际超过大小限制
- **THEN** 系统 SHALL 中止接收并返回 413，清理 multipart 临时资源和业务临时文件，不登记视频

#### Scenario: 空文件或中断
- **WHEN** 上传空文件、连接中断、磁盘写入或元数据登记失败
- **THEN** 空文件 SHALL 返回 400，其余失败 SHALL 明确暴露；本次部分文件和元数据 SHALL 不残留

### Requirement: 封面生成不阻塞 API 事件循环

封面抽帧 SHALL 在受限执行器中进行，保留超时与失败降级，失败不得使已持久化视频丢失。

#### Scenario: 抽帧仍在等待
- **WHEN** 抽帧子进程被测试屏障阻塞且另一个健康请求到达
- **THEN** 健康请求 SHALL 在解除抽帧屏障前完成

#### Scenario: 抽帧失败
- **WHEN** FFmpeg 缺失、解码失败或超时
- **THEN** 上传登记 SHALL 保持成功，封面 SHALL 标记缺失并清理半成品
