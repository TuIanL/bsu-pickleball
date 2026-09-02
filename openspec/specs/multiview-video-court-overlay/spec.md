# multiview-video-court-overlay Specification

## Purpose

规定识别分析页主视频中基于真实场地标定和人工球网标注的空间投影层，以及多摄像机展示切换时几何资产与视频时间的一致性。

## Requirements

### Requirement: 主视频显示当前机位的球场投影

识别分析页 SHALL 在主视频的同一画面坐标系中显示当前展示机位的球场外框，并可显示标准球场的厨房线和中线。投影 SHALL 使用当前机位的有效 court calibration 几何，不得绘制静态示意矩形代替真实标定结果。

#### Scenario: 当前机位存在有效四角标定

- **WHEN** 当前展示机位拥有有效的球场→图像 homography 和媒体尺寸
- **THEN** 主视频 SVG SHALL 将球场四个标准角点投影到当前视频画面
- **AND** 外框 SHALL 与该机位人工标定的四个角点重合到标定误差范围内
- **AND** 球场线 SHALL 与人物框、骨架和球图层共享同一视频 `viewBox`

#### Scenario: 标定尺寸与视频尺寸不同

- **WHEN** 标定图像尺寸与当前视频自然尺寸不同但两者均有效
- **THEN** renderer SHALL 按记录的宽高把投影结果归一化到当前视频尺寸
- **AND** `preserveAspectRatio="xMidYMid meet"` 下球场线 SHALL 与视频内容保持空间对齐

#### Scenario: 当前机位缺少有效球场标定

- **WHEN** 当前机位没有 calibration、homography 无效或质量状态不可用
- **THEN** 主视频 SHALL 隐藏球场投影层
- **AND** 页面 SHALL 显示“球场投影不可用”或等价原因
- **AND** 页面 SHALL NOT 显示模拟矩形或沿用上一机位的球场几何

### Requirement: 主视频显示当前机位的人工球网标注

当当前机位拥有已确认的球网左端、中心和右端 image-space 标注时，主视频 SHALL 在当前视频坐标系中绘制球网顶部曲线或折线。球网层 SHALL 与球场层独立加载和独立显示；本版本不得将二维曲线描述为完整三维网面或实测飞行遮挡。

#### Scenario: 当前机位拥有完整三点球网标注

- **WHEN** 当前 view 的 metric scene revision 包含已确认的左端、中心、右端球网 image-space 点
- **THEN** 主视频 SHALL 绘制经过三个控制点的球网顶部曲线或等价折线
- **AND** 球网标注 SHALL 使用当前 view 的图像尺寸进行缩放
- **AND** 球网 SHALL 与当前机位的视频近远方向一致

#### Scenario: 球网标注缺失但球场标定存在

- **WHEN** 当前 view 的球场 calibration 可用但球网 scene revision 或必需三点不完整
- **THEN** 主视频 SHALL 保留球场投影层
- **AND** SHALL 隐藏球网投影层并显示球网标注不可用原因
- **AND** SHALL NOT 使用固定屏幕中线伪造球网

#### Scenario: 用户关闭球网投影

- **WHEN** 用户关闭球网投影开关
- **THEN** 主视频 SHALL 隐藏球网曲线
- **AND** 球场外框、人物框、骨架、球点、球路、弹跳候选和小地图状态 SHALL 保持不变

### Requirement: 球场和球网图层可独立控制

主视频 SHALL 为球场投影和球网投影提供独立、可观察状态的控制。控制不可用时 SHALL 说明对应几何资产原因，切换控制不得改变媒体播放时间或 canonical 分析数据。

#### Scenario: 用户只关闭球场投影

- **WHEN** 用户关闭球场投影但保持球网投影开启
- **THEN** 主视频 SHALL 隐藏球场外框和场地线
- **AND** 若球网资产可用 SHALL 继续显示球网层

#### Scenario: 图层资产正在加载

- **WHEN** 视频已经可播放但当前机位的几何资产仍在加载
- **THEN** 视频播放 SHALL 保持可用
- **AND** 对应投影控制 SHALL 显示 loading 或不可用状态
- **AND** SHALL NOT 显示旧机位几何或静态占位几何

### Requirement: A/B 机位切换同步切换投影几何

双摄任务在展示机位切换时 SHALL 将目标视频、source timestamp mapping、court calibration、球网标注和展示方向视为同一目标 view。目标 view 准备完成前，系统 SHALL 不使用上一 view 的球场或球网几何。

#### Scenario: 播放中从 A 切换到 B

- **WHEN** 用户在视频播放期间从 A 机位切换到 B 机位
- **THEN** B 视频 SHALL seek 到与切换前相同的 canonical 时间
- **AND** B 的球场外框和球网标注 SHALL 替换 A 的对应图层
- **AND** 目标 seek 完成后 SHALL 按切换前播放状态继续播放
- **AND** A 的旧视频事件不得再更新 B 的 overlay 时间或几何

#### Scenario: 暂停时从 B 切换回 A

- **WHEN** 用户在暂停状态从 B 机位切换回 A 机位
- **THEN** A 视频 SHALL 定位到等价 canonical 时间并保持暂停
- **AND** A 的球场和球网几何 SHALL 与 A 的标定数据一致

#### Scenario: 往返切换

- **WHEN** 用户连续执行 A→B→A 切换
- **THEN** 每次 SHALL 使用对应 view 的独立几何资产
- **AND** SHALL 不出现上一 view 的几何残留、累计缩放或方向二次翻转

### Requirement: 固定机位与标定降级语义明确

系统 SHALL 将主视频球场/球网投影定义为 fixed-camera 静态标定能力，不得在本功能中暗示摄像机移动后仍能保持准确。资产缺失、尺寸不匹配或质量门未通过时 SHALL 降级隐藏相应图层并保留可解释状态。

#### Scenario: 固定机位正常播放

- **WHEN** 摄像机位置、焦距、裁切和视频尺寸在播放期间保持固定
- **THEN** 系统 SHALL 复用该 view 的静态几何资产
- **AND** 不得在每个视频帧发起网络请求或重新计算完整标定

#### Scenario: 摄像机发生移动或变焦

- **WHEN** 视频内容显示摄像机移动、旋转、数字变焦或裁切变化
- **THEN** 系统 SHALL 将静态投影标记为可能失准或由质量策略隐藏
- **AND** SHALL NOT 声称已完成逐帧相机跟踪

### Requirement: 投影层不改变既有分析数据和播放性能

球场和球网投影 SHALL 只改变主视频的显示层，不得修改 canonical 球员坐标、球路、弹跳事件、身份颜色、时间映射或分析指标。静态几何 SHALL 被缓存和 memoize，避免影响 60 FPS 视频播放及现有人物/球图层刷新。

#### Scenario: 播放期间显示投影层

- **WHEN** 用户播放 60 FPS 真实视频并开启球场/球网投影
- **THEN** 投影层 SHALL 跟随当前视频元素显示
- **AND** 现有人物框、骨架和球图层 SHALL 继续按 canonical 时间更新
- **AND** 静态几何不得在每个视频帧重复读取 API

#### Scenario: 切换投影开关

- **WHEN** 用户任意切换球场或球网投影开关
- **THEN** 视频 currentTime、播放/暂停状态和所有分析 artifact 数据 SHALL 保持不变
