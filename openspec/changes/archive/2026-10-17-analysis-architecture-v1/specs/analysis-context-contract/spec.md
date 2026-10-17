## ADDED Requirements

### Requirement: 上下文按消费字段冻结和绑定
系统 SHALL 将来源媒体、时间映射、标定、名册、身份和回合信息表达为版本化 ContextSnapshot。实现 MUST 声明实际消费字段；计划 SHALL 冻结相关值与摘要，缓存 SHALL 仅绑定该消费投影。运行时不得读取可变的最新配置替代已冻结上下文。

#### Scenario: 原始检测不消费球场语义
- **WHEN** ball.detect 只消费媒体和帧时间
- **THEN** 名册、比分及标定 SHALL 不成为其运行前提或缓存失效来源

#### Scenario: 显式使用名册的消费者
- **WHEN** 一个 fixture 消费 roster 的队伍与端位字段
- **THEN** 对应快照变化 SHALL 改变其计算身份
- **AND** SHALL 不使无关图像检测分支失效

### Requirement: 媒体和时间身份可以核验
源身份 SHALL 包含不可变媒体版本或强内容摘要，及消费的 PTS sidecar/同步映射摘要。路径、文件大小或 mtime 单独 MUST NOT 被当作可靠内容身份。已登记源被替换或摘要无法核验时，运行 SHALL 拒绝复用旧缓存并要求显式登记新版本或报告稳定错误。

#### Scenario: 原路径替换内容
- **WHEN** 相同 video_id/路径下的视频内容被替换
- **THEN** 系统 SHALL 识别版本不符或产生新来源身份
- **AND** SHALL 不继续使用旧帧观测缓存

#### Scenario: PTS 修改
- **WHEN** 媒体内容不变但被消费的 PTS/同步快照变化
- **THEN** 相关时间映射计划和产物 SHALL 使用新的身份

### Requirement: 帧与时间坐标明确
每个帧观测 SHALL 保留 view_id、source_frame_index、source_pts 和映射到公共时间的方式/状态。单摄可声明 source 时间为运行基准；正式双摄 MUST 使用已冻结的 PTS 与同步映射，禁止用 nominal FPS 替换权威映射。

#### Scenario: 双摄延迟与映射
- **WHEN** 同一 canonical tick 映射到两个不同 source frame
- **THEN** 产物 SHALL 分别记录 source 与 canonical 时间
- **AND** SHALL 不假设两个机位具有相同帧索引

### Requirement: 主体标识具有作用域且不伪造稳定身份
检测 observation、view-local track 和 global player SHALL 使用不同主体类型与命名空间。标识 MUST 绑定来源、机位和相应帧/运行 epoch；unknown 与 ambiguous 必须可表达。未执行关联的姿态 SHALL 使用 observation-scoped 主体，并显式关闭或隔离依赖稳定 track_id 的历史状态。

#### Scenario: 检测框顺序变化
- **WHEN** 相邻帧的人框排序改变而没有跟踪输入
- **THEN** 系统 SHALL 不把框序号解释为跨帧稳定球员
- **AND** 依赖 track_id 的姿态可见性状态 SHALL 不串到另一个人

#### Scenario: 两个机位同名 track
- **WHEN** cam_1 与 cam_2 都出现 local track 1
- **THEN** 它们 SHALL 是不同主体
- **AND** 只有显式关联证据才可指向同一个 global player

### Requirement: 空间单位和标定有效域不隐含转换
产物类型 SHALL 声明 image_px、normalized_image、court_m 或 world_3d 等坐标系、单位、机位及所需标定/有效时间域。需要空间换算的实现 MUST 验证标定，原始人/球/姿态图像观测 MUST NOT 因缺标定被整体阻断。

#### Scenario: 二维姿态运动证据
- **WHEN** 仅由图像关键点求位移或速度
- **THEN** 输出 SHALL 声明 px 或 px/s 等真实单位
- **AND** SHALL 不将其包装为米制速度、真实关节力矩或生物力学结论

#### Scenario: 标定过期
- **WHEN** 消费 court_m 的 fixture 获得不覆盖目标时间域的标定
- **THEN** 系统 SHALL 拒绝该输入或按契约输出证据不足
- **AND** SHALL 不静默使用其他时段的最新标定
