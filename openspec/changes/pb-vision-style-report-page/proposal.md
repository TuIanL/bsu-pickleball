## Why

现有报告页面（ReportPage）采用较克制的深绿单页流式布局，与行业标杆产品 PB Vision 在视觉冲击力、信息层次感、产品化呈现上存在显著差距。为了给前期展示评审提供更具专业感和产品感的界面，我们将报告页面整体改造为 PB Vision 风格的亮色主题 + 左侧球员抽屉栏 + 卡片化模块流，同时复用已有的 Three.js 3D 球场轨迹、ECharts 热力图、技能评分等可视化能力，降低重复开发成本。

## What Changes

- 报告页（`/report/:id`）新增**仅在本页可见的左侧临时抽屉栏**（260px 宽，可折叠），包含导航图标、当前比赛球员头像快速切换列表、亮绿色 Share 按钮
- 整站**主题色板替换为 PB Vision 亮色风格**：主色从深绿改为荧光亮绿（#00FF41），搭配白底卡片 + 6 维度专属彩色（紫/蓝/青/红橙/金/粉）
- **球员信息顶部横卡**：头像 + 姓名 + 总击球数 + 进区率（In%）进度条 + 球速/挥拍速度百分位进度条
- **Skill Rating 区完全重制**：从原 SVG 六轴雷达图改为「综合大数字 + 彩色 6 分饼图 + 6 张彩色维度卡片」风格
  - ⚠️ 无球员历史数据时，"长期平均分对比线"和"维度 Δ 变化值"不显示，但 DOM 结构和 CSS class 预留占位以便未来接入
- **Court Coverage 区**：跑动距离数值 + 密度热力图（色板改为黄→绿→粉 PB 风格渐变）
- **Serves & Returns 区**：发球/接发 In/Out 进度条 + Depth 条形图 + 双环形图（Serve Depth / Return Depth）
- 新增 **Filter 工具栏**（3D 球场下方）：击球阶段下拉、击球类型下拉、Shot Quality 质量滑块
- **Coach's Insight 区**：改为米黄底色卡片 + 教练头像占位 + 建议文字 + 3D 球场小预览缩略图
- **Legal Thirds 区**：灯泡图标 + 建议文字 + 亮绿色跳转按钮（链接占位，未来接训练页/视频）
- 复用现有 `BallTrajectoryScene` Three.js 3D 球场组件，仅调整容器圆角和视角切换按钮样式使其匹配 PB 风格

## Capabilities

### New Capabilities
- `pb-vision-style-report`: 报告页 PB Vision 风格整体呈现能力，包含左侧临时抽屉栏、亮色主题、球员信息顶卡、Skill Rating 饼图+彩色维度卡、Court Coverage、Serves & Returns、Coach's Insight、Legal Thirds、Filter 工具栏等新增可视化模块及布局规范

### Modified Capabilities
- `report-detail-pages`: 报告详情页的渲染路径和默认展示组件替换为 PB Vision 风格（原 ReportPage 组件保留为 fallback，路由默认走新风格）
- `interactive-performance-report`: 表现洞察交互面板纳入 PB 风格卡片容器，适配新配色和球员抽屉切换逻辑
- `frontend-viz-beautification`: 热力图色板扩展增加 PB 风格黄→绿→粉渐变，并新增维度专属彩色变量

## Impact

**Affected code**:
- `src/pages/ReportPage.tsx` — 整页替换为 PB 风格布局骨架（原内容作为 fallback 分支）
- `src/index.css` — 新增/替换 PB Vision 亮色主题 CSS 变量和组件公用样式
- `src/components/platform/` 目录下新增 9 个 PB 风格组件（详见 design.md）
- `src/hooks/` — 新增 `useReportPbStyle` 或类似 hook 封装当前选中球员、过滤状态

**Affected APIs / dependencies**:
- 后端 API 无 breaking change；所有无对应字段的模块（Serves/Returns Depth、Δ值、长期平均）均采用前端 mock 并预留数据接入点
- 前端依赖无新增（复用已有 echarts / three / tailwind）

**Affected systems**:
- 报告页（`/report/:id`）单独生效，首页、录制页、分析工作区等其他页面和全局 AppShell 不受影响
