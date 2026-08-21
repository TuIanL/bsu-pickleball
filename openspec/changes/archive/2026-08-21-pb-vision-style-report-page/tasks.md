## 1. 主题系统与 Mock 数据基础设施（完成后即有骨架可跑）

- [x] 1.1 在 `index.css` 中新增 `.pb-vision-theme` 作用域 + 全套 `--pb-*` 变量（主色/页底/卡片/文字/6 维专属彩色/热力图三段渐变）
- [x] 1.2 新建 `src/utils/pbMockData.ts`，导出 `mockInPercent / mockSpeedPercentile / mockServeReturnStats / mockServeReturnDepth` 四个纯函数
- [x] 1.3 新建 `src/types/pbReport.ts` 类型声明（PbReportContext 值、Filter 类型、mock 返回结构等）
- [x] 1.4 新建 `src/contexts/PbReportContext.tsx` + `usePbReport()` hook，实现 Context Provider（selectedPlayerId/stageFilter/typeFilter/qualityThreshold/drawerOpen + setter + 派生计算值 memo）

## 2. 报告页容器与左侧抽屉栏（P0 布局骨架）

- [x] 2.1 新建 `src/components/pb-vizion/PbVisionReportLayout.tsx`（组件目录命名 pb-vizion 防止和变量名冲突），挂载 `.pb-vision-theme` class 并注入 PbReportContext.Provider
- [x] 2.2 新建 `PbPlayerDrawer.tsx`（抽屉栏）：fixed 定位 260px 宽、顶部导航图标列表（5 项，视觉占位）、中部球员头像列表（从 subjects 读取，点击触发 setSelectedPlayerId 并加高亮选中态）、底部亮绿色 Share 按钮（onClick 弹 toast 占位）
- [x] 2.3 抽屉栏新增折叠/展开按钮（右上角 × + 侧边展开条），并在 Layout 中同步控制主内容 `pl-[260px]` / `pl-0`
- [x] 2.4 修改 `ReportPage.tsx`：读取 `searchParams.legacy` 和 `localStorage.reportLegacy`，条件分支挂载 `<PbVisionReportLayout report={report} />`（默认）或原有旧布局（legacy=true 时）
- [x] 2.5 手动验证：访问 `/report/demo-double` 默认显示 PB 布局（左侧抽屉）；加 `?legacy=1` 显示旧布局；跳首页配色不变

## 3. 球员信息顶卡 + Skill Rating 核心区（P0 主体内容）

- [x] 3.1 新建 `PbPlayerHeaderCard.tsx`：圆形头像占位 + 球员姓名 + Total Shots 数值 + In% 荧光亮绿进度条 + Ball Speed 行（数值 + Percentile 标签 + 进度条）+ Paddle Speed 行（同上）。从 usePbReport 取 selectedPlayerId，真实值优先/缺省走 pbMockData
- [x] 3.2 新建 `PbSkillPieChart.tsx`：ECharts pie 6 扇区（按 6 个维度专属彩色），中心无 label，配合 legend 或 tooltip；输入 `Record<DimensionKey, score01>`
- [x] 3.3 新建 `PbSkillRatingSection.tsx`：布局容器（综合大数字 + 饼图 + 空占位 `pb-long-term-compare` DOM + 2×3 卡片网格）
- [x] 3.4 在 Skill 节中渲染 6 张彩色维度卡组件（PbSkillDimCard 内联实现）：每张卡浅彩底 + 深彩边 + 标题彩色字 + 分数。分数由 skillRatings.dimensions 映射到 2.0~5.5 区间（公式 sum/6/10*3.5+2）。卡片下方渲染空占位 `pb-dim-delta` DOM（不显示 Δ 值）
- [x] 3.5 手动验证：切换抽屉栏球员，顶卡、分数、饼图同步刷新

## 4. 3D 球场整合 + Filter 工具栏

- [x] 4.1 新建 `Pb3DCourtCard.tsx`：外层白底 rounded-2xl 卡片容器，内部直接渲染现有 BallTrajectoryScene。将传入 report/selectedPlayerId 等 props 适配好
- [x] 4.2 修改 3D 球场右侧视角按钮样式：在 BallTrajectoryScene 外层包一层 CSS class（`.pb-3d-view-btns`），将按钮改为白底 1px 边框方钮 + 选中时亮绿边框（不修改组件内部逻辑）
- [x] 4.3 新建 `PbFilterToolbar.tsx`：击球阶段下拉（All Shots/Serves/3rd Shots/5th+ Shots 默认）+ 击球类型下拉（All + 各 ShotType 枚举）+ Shot Explorer 按钮（占位 toast）+ Shot Quality 原生 range 滑块（0~100，默认 70）+ 右侧实时百分比数字
- [x] 4.4 Filter 与 3D 球场联动：将 stageFilter/typeFilter/qualityThreshold 通过 Context 作用到 BallTrajectoryScene 的过滤逻辑上（若现有组件不支持外部 props 过滤，则在 Pb3DCourtCard 内部先对 shotRows/trajectories 做预处理再传入）

## 5. Court Coverage + Serves & Returns 可视化模块（P1）

- [x] 5.1 修改 `StructuredZoneHeatmap.tsx`：增加可选 prop `colorScheme?: 'platform' | 'pb-vision'`；传入 pb-vision 时用 PB 6 段渐变色（#00FF41 → #34D399 → #22D3EE → #6366F1 → #A855F7 → #7E22CE）球网亮绿线，厨房虚线紫色
- [x] 5.2 新建 `PbCourtCoverage.tsx`：Distance Covered 标题（从 metrics.distances 取，单位 ft.）+ 球场热力图（用 `colorScheme="pb-vision"`）；若 metrics.heatmap 空则用 movementPath 聚合生成密度（为空则展示球场 SVG 底框占位）
- [x] 5.3 新建 `PbServesReturns.tsx` 整体容器 + Serves In/Out 进度条（Total 数 + 亮绿 In 条）+ Returns In/Out 进度条（末尾洋红 Net 小块）
- [x] 5.4 在 PbServesReturns 中新增 Serve & Return Depth 子块：左侧 3 层条形图（Deep 绿/Medium 金/Shallow 红橙，长度按百分比），右侧两个 ECharts 甜甜圈环形图（Serve Depth、Return Depth），数据从 pbMockData.mockServeReturnDepth 读取

## 6. Coach's Insight + Legal Thirds 收尾卡（P2）

- [x] 6.1 新建 `PbCoachInsight.tsx`：米黄背景 (#FFF7E6) 卡片，左侧圆形教练头像占位 + "Coach's Insight" 小标题 + 建议大字（从 findings[0].content 或 recommendations[0] 取）+ 右侧 3D 球场缩略预览（SVG 占位图）
- [x] 6.2 新建 `PbLegalThirds.tsx`：💡灯泡图标 + "Percentage of Legal Thirds" 标题 + 建议段落文字（从 coachNotes / trainingRecommendations 里筛选第三拍相关，无匹配则用一段通用中文建议占位）+ 亮绿色 "Take a look at your shots here →" 按钮（onClick preventDefault + console.warn 占位，href=#）
- [x] 6.3 PerformanceInsightsPanel 适配：仅在 legacy 分支保留原有样式；PB 新报告页不渲染此面板（避免主题冲突）

## 7. PbVisionReportLayout 整合串联 + 最终验证

- [x] 7.1 在 PbVisionReportLayout 的主内容区按最终顺序依次渲染：PbPlayerHeaderCard → Pb3DCourtCard → PbFilterToolbar → PbSkillRatingSection → (Court Coverage 左 + Serves&Returns 右 2 列栅格) → (Coach Insight 左 + Legal Thirds 右 2 列栅格)；所有卡片用 pb-card 样式
- [x] 7.2 响应式兜底：< 1200px 宽时把两列栅格都改成单列堆叠（至少保证不横向溢出不崩溃）（用 `lg:grid-cols-2`，<lg 单列）
- [x] 7.3 验证所有切换：抽屉栏折叠/展开、球员切换、Filter 过滤（阶段/类型/质量滑块）都能即时更新对应可视化（需手动打开 dev server 验证）
- [x] 7.4 跑 `npm run lint` + `npm run typecheck`，修复所有 PB 相关 TS 类型和 ESLint 报错（3 errors 修完，只剩 2 个 Fast refresh warning 可接受）
- [x] 7.5 回归检查：`?legacy=1` 旧报告页视觉和改造前一致；首页/分析页/录制页视觉零差异；无主题泄漏（需手动验证）
- [x] 7.6 （可选增强）在抽屉栏底部加一个 "切换旧版" 小按钮，点击写入 localStorage 并刷新，方便演示 AB 对比
