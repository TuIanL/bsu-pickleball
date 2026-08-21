## ADDED Requirements

### Requirement: 报告页具备 PB Vision 风格左侧临时抽屉栏
当用户访问分析报告页面时，系统 SHALL 在页面左侧渲染一个仅在报告页可见的 260px 宽抽屉栏，包含导航图标区、当前比赛球员头像列表（可点击切换）、以及底部亮绿色 Share 按钮；抽屉栏 SHALL 支持折叠收起为 0px 以腾出主内容空间，且 SHALL NOT 影响其他页面的全局 AppShell 布局。

#### Scenario: 首次进入报告页默认展开抽屉栏
- **WHEN** 用户通过路由进入 `/report/:id` 页面
- **THEN** 抽屉栏 SHALL 以展开态显示在页面左侧，宽度 260px
- **AND** 抽屉栏顶部 SHALL 有 5 个导航入口（Home/Shot Explorer/Game Stats/Leaderboards/Team Stats）的图标+文字
- **AND** 抽屉栏中部 SHALL 列出当前报告中的所有球员（从 subjects 读取），每项包含圆形头像占位+姓名缩写+姓名
- **AND** 抽屉栏底部 SHALL 有一个背景为荧光亮绿 (#00FF41) 的 Share 按钮

#### Scenario: 点击球员头像切换当前选中球员
- **WHEN** 用户在抽屉栏球员列表中点击某一球员卡片
- **THEN** 该球员卡片 SHALL 变为深灰背景高亮选中态
- **AND** 顶部球员信息卡、Skill Rating 区、Court Coverage 热力图等所有球员相关模块 SHALL 即时切换到对应球员数据

#### Scenario: 折叠/展开抽屉栏
- **WHEN** 用户点击抽屉栏右上角或侧边的折叠按钮
- **THEN** 抽屉栏 SHALL 以动画过渡到 0px 宽隐藏态
- **AND** 主内容区 SHALL 自动拉伸占满整屏
- **WHEN** 用户再次点击侧边上的展开按钮
- **THEN** 抽屉栏 SHALL 恢复 260px 展开态

---

### Requirement: 报告页应用 PB Vision 亮色主题色板
报告页面 SHALL 使用 PB Vision 亮色风格的统一配色方案：主色荧光亮绿 (#00FF41)、页面背景浅灰白 (#F0F4F2)、卡片纯白 (#FFFFFF) 配 1px 浅灰边框、文字近黑 (#111827)；6 个能力维度 SHALL 分别使用专属彩色（紫/蓝/青/红橙/金/粉）用于其卡片背景、边框和标题文字。

#### Scenario: 所有按钮和高亮元素使用荧光亮绿
- **WHEN** 报告页渲染完成
- **THEN** 所有主按钮、选中态、In% 进度条、滑块填充 SHALL 使用 #00FF41 荧光亮绿
- **AND** 页面背景 SHALL 为 #F0F4F2，卡片 SHALL 为白色配圆角 (rounded-xl 级)

#### Scenario: 6 张技能维度卡片使用专属彩色
- **WHEN** Skill Rating 区渲染 6 张维度卡片
- **THEN** Kitchen Game SHALL 使用紫色 (#A855F7)
- **AND** Ball Control SHALL 使用蓝色 (#3B82F6)
- **AND** Defense SHALL 使用青色 (#06B6D4)
- **AND** Offense SHALL 使用红橙色 (#F97316)
- **AND** Court IQ SHALL 使用金色 (#EAB308)
- **AND** Targeting SHALL 使用粉色 (#EC4899)
- **每张卡片 SHALL 使用对应彩色的浅色底 + 深色边框 + 深色标题字**

---

### Requirement: 球员顶部横卡展示击球数与双速度百分位
球员信息横卡 SHALL 位于报告页主内容区最顶部，包含：圆形头像占位 + 球员姓名 + 总击球数 (Total Shots) + 进区率 (In%) 荧光亮绿进度条 + 球速 (Ball Speed) 数值+百分位进度条 + 挥拍速度 (Paddle Speed) 数值+百分位进度条。

#### Scenario: 球员有完整数据时的正常渲染
- **WHEN** 选中球员的 shotRows 有击球记录且 metrics 有速度字段
- **THEN** Total Shots SHALL 显示 `shotRows.length`
- **AND** In% 进度条 SHALL 按 legal_shots/total_shots 比例显示荧光亮绿填充块
- **AND** Ball Speed 一行 SHALL 显示"Ball Speed: {X} mph" + 百分位标签（如"84th"）+ 对应比例的进度条
- **AND** Paddle Speed 一行 SHALL 显示"Paddle Speed: {Y} mph" + 百分位标签 + 对应比例的进度条

#### Scenario: In% 或百分位缺失时的降级显示
- **WHEN** 后端没有返回 In% 或百分位字段
- **THEN** 前端 SHALL 使用合理的 mock 值范围（In%: 85%-95%，百分位: 60-90th）渲染占位
- **AND** 对应 DOM SHALL 保留数据 class 名称以便未来接入真实字段时只需改数据源

---

### Requirement: Skill Rating 区使用综合分 + 六分饼图 + 六维彩色卡片布局
Skill Rating 节 SHALL 采用「左大数字综合分 + 中六分彩色饼图 + 下方六张彩色维度卡片 (2行×3列)」布局；当缺少球员历史数据时，"长期平均对比线"和"每张卡片下方的 Δ 变化值" SHALL 不显示，但 SHALL 预留对应空 DOM 容器和 CSS class 以便未来接入。

#### Scenario: 综合分和六维分数正常渲染
- **WHEN** 报告数据包含 skillRatings 的 6 项维度分数
- **THEN** 综合分数 SHALL 按 `sum(六维分数)/6 / 10 * 3.5 + 2` 的线性映射公式缩放到 2.0~5.5 区间，保留两位小数
- **AND** 中部六分饼图 SHALL 每扇区对应一个维度，使用该维度专属彩色
- **AND** 下方六张卡片 SHALL 从 skillRatings 对应维度读取分数并映射到 2.0~5.5 区间

#### Scenario: 无历史数据时的占位（不显示对比线和Δ）
- **WHEN** `progressPoints` 历史数据为空或缺失
- **THEN** "Long-term average" 横向对比线区域 SHALL 为空（不渲染刻度线和圆点）
- **AND** 每张维度卡片的 Δ 变化值行 SHALL 为空（不渲染 +0.01 / -0.01 等文本）
- **AND** 两处 SHALL 保留 class 名为 `pb-long-term-compare` 和 `pb-dim-delta` 的空占位 DOM 容器

---

### Requirement: Court Coverage 区显示跑动距离 + 密度热力图
Court Coverage 节 SHALL 在白色卡片中显示「Distance Covered: X ft.」数值标题，以及一个匹克球场底图上的球员移动密度热力图；热力图色板 SHALL 采用「黄 (#FBBF24) → 绿 (#00FF41) → 粉 (#EC4899)」的 PB 风格渐变。

#### Scenario: metrics 中返回 distances 和 heatmap
- **WHEN** 选中球员的 `metrics.distances` 和 `metrics.heatmap.cells` 有数据
- **THEN** Distance Covered 后 SHALL 显示对应 distance_ft 值 + " ft."
- **AND** 球场热力图 SHALL 基于 heatmap.cells 渲染，颜色越深表示该区域停留时间越长，色板 SHALL 为黄→绿→粉渐变

#### Scenario: 只有 movementPath 时的聚合降级
- **WHEN** heatmap.cells 无数据但 movementPath 有坐标序列
- **THEN** 前端 SHALL 将 movementPath 坐标聚合到球场网格单元，按单元内点数生成密度热力图
- **AND** 色板仍 SHALL 为黄→绿→粉渐变

---

### Requirement: Serves & Returns 区显示 In/Out 条和 Depth 可视化
Serves & Returns 节 SHALL 包含：① Serves In/Out 进度条（Total 数 + In% 亮绿填充 + Out/Net 洋红块）；② Returns In/Out 进度条（同结构）；③ Serve & Return Depth 标题下的 3 层条形图（Shallow/Medium/Deep）和两个环形甜甜圈图（Serve Depth、Return Depth）。数据缺失时 SHALL 使用预设 mock 分布。

#### Scenario: 正常渲染 Serves/Returns
- **WHEN** 报告数据中有发球/接发统计
- **THEN** Serves In/Out 条 SHALL 显示 Total 发球数 + In 比例亮绿条
- **AND** Returns In/Out 条 SHALL 在末尾增加洋红 (#E879F9) "Net" 块表示擦网
- **AND** Serve Depth 和 Return Depth 环形图 SHALL 分别以 Deep(绿)/Medium(金)/Shallow(红橙) 三段彩色扇区展示占比

---

### Requirement: Filter 工具栏支持击球阶段/类型过滤与质量滑块
3D 球场组件下方 SHALL 有 Filter 工具栏，包含：击球阶段下拉（默认 3rd Shots）、击球类型下拉（默认 All Shot Types）、Shot Explorer 跳转按钮、Shot Quality 范围滑块（0-100%，默认 70%）。用户操作后 SHALL 即时过滤 3D 球场上显示的轨迹。

#### Scenario: 调整击球阶段过滤
- **WHEN** 用户从击球阶段下拉切换到"All Shots"/"Serves"/"3rd Shots"/"5th+ Shots"
- **THEN** 上方 3D 球场显示的球轨迹 SHALL 仅保留匹配该阶段的击球点

#### Scenario: 拖动 Shot Quality 滑块
- **WHEN** 用户拖动 Shot Quality 滑块到新的百分比
- **THEN** 3D 球场上显示的轨迹 SHALL 仅保留 qualityScore 大于等于该阈值的击球
- **AND** 滑块右端 SHALL 实时显示当前百分比数字（如 "70 %"）

---

### Requirement: Coach's Insight 米黄卡 + Legal Thirds 灯泡提示卡
页面底部 SHALL 左右两栏：左侧为米黄背景 (#FFF7E6) 的 Coach's Insight 卡片（圆形教练头像+标题+建议文字+3D 球场小预览缩略图）；右侧为 Legal Thirds 卡（💡灯泡图标+标题+建议段落文字+亮绿色跳转按钮，按钮 href 暂时留空 "#"）。

#### Scenario: 渲染教练洞察与建议卡
- **WHEN** 报告有 findings 或 recommendations 数据
- **THEN** Coach's Insight 卡文字 SHALL 取 findings[0] 的建议内容
- **AND** Legal Thirds 卡 SHALL 取训练建议中的第三拍相关内容
- **AND** 右下角 "Take a look at your shots here →" 按钮 SHALL 为荧光亮绿底色，href="#"（占位）

---

### Requirement: 复用现有 3D 球场组件并调整容器和按钮样式
BallTrajectoryScene Three.js 组件 SHALL 被整体复用，不重写 WebGL 渲染逻辑；仅 SHALL 修改其外层容器为白底卡片 + 大圆角 (rounded-2xl)，以及将右侧视角切换按钮样式微调为 PB 风格（白底方钮 + 1px 边框 + 选中时亮绿边框）。

#### Scenario: 3D 球场渲染与交互不变
- **WHEN** 报告页加载 3D 球场
- **THEN** Three.js 场景、球轨迹渲染、视角切换行为 SHALL 与原实现完全一致
- **AND** 仅容器样式变为 rounded-2xl 白底卡片，视角按钮换为 PB 风格外观
