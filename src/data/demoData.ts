import type {
  CoachNote,
  DashboardMetric,
  Diagnosis,
  DrillRecommendation,
  HardwarePreview,
  Highlight,
  MatchSummary,
  NavigationItem,
  OverviewCard,
  PlayerMarker,
  ProgressPoint,
  ReportAction,
  AnalysisReport,
  ReportDefinition,
  ReportSession,
  SkillRating,
  TimelineMarker,
  TrainingRecommendation,
  VideoOverlayLabel,
} from "../types/report";
import { productCopy } from "./productCopy";

export const reportSession: ReportSession = {
  athlete: "球馆体验用户 A",
  venue: "北京体育大学匹克球训练场",
  date: "2026-05-04",
  level: "大众进阶",
  reportId: "PV-20260504-018",
  summary:
    "本次样例聚焦人员移动、站位覆盖和回位节奏，用于展示当前保留的视觉分析工作流。",
  metrics: [
    {
      id: "overall",
      label: "综合评分",
      value: "86",
      detail: "移动覆盖和回位节奏优于同级样本",
      trend: "+8",
      direction: "up",
    },
    {
      id: "speed",
      label: "最高移动速度",
      value: "5.4 m/s",
      detail: "人员移动片段速度峰值",
      trend: "+5 km/h",
      direction: "up",
    },
    {
      id: "movement",
      label: "移动效率",
      value: "78%",
      detail: "回位路径存在 2 次绕行",
      trend: "-4%",
      direction: "down",
    },
    {
      id: "rally",
      label: "连续移动",
      value: "12 段",
      detail: "最长连续位移片段",
      trend: "持平",
      direction: "steady",
    },
    {
      id: "accuracy",
      label: "覆盖准确",
      value: "72%",
      detail: "目标站位覆盖率",
      trend: "+6%",
      direction: "up",
    },
  ],
  landingPoints: [],
  routes: [],
  movementPath: [
    { x: 50, y: 83 },
    { x: 38, y: 74 },
    { x: 31, y: 66 },
    { x: 44, y: 58 },
    { x: 63, y: 64 },
    { x: 70, y: 72 },
    { x: 54, y: 81 },
    { x: 48, y: 83 },
  ],
  rallies: [],
};

export const diagnoses: Diagnosis[] = [
  {
    id: "backswing",
    issue: "引拍滞后",
    severity: "中",
    evidence: "当前样例仅保留姿态诊断占位，真实任务需等待姿态模型输出。",
    suggestion: "在反手准备阶段提前完成肩髋转向，降低拍头等待时间。",
    expectedOutcome: "后续用姿态关键点替换样例说明。",
    priority: "优先级 1",
  },
  {
    id: "balance",
    issue: "重心偏移",
    severity: "高",
    evidence: "中场连续相持时，身体重心 4 次偏离支撑脚连线外侧。",
    suggestion: "加入分腿垫步和小碎步回位训练，限制移动后身体继续外飘。",
    expectedOutcome: "提升下一段启动速度，稳定连续移动质量。",
    priority: "优先级 2",
  },
  {
    id: "backhand-placement",
    issue: "右侧回位稳定性不足",
    severity: "中",
    evidence: "右侧覆盖后的恢复路径更长，平均回位效率低于左侧。",
    suggestion: "以 3 组 45 秒为单位练习右侧横移后的回位节奏。",
    expectedOutcome: "缩短恢复路径，为后续位移投影提供更稳定样本。",
    priority: "优先级 3",
  },
];

export const trainingRecommendations: TrainingRecommendation[] = [
  {
    id: "tr1",
    issueId: "backswing",
    title: "反手提前引拍对标",
    learningContent: "教学视频占位：反手准备节奏与肩髋转向",
    practiceTask: "连续 4 组反手准备节奏练习，记录启动和回位耗时。",
    nextTarget: "下次训练右侧回位效率达到 68%",
    progress: {
      previous: 55,
      current: 61,
      target: 68,
      unit: "%",
    },
  },
  {
    id: "tr2",
    issueId: "balance",
    title: "分腿垫步与回位路径",
    learningContent: "动作对标占位：移动后的第一步启动与回位路径",
    practiceTask: "完成 6 轮中场相持-回位训练，每轮 45 秒，重点观察回位耗时。",
    nextTarget: "平均回位时间从 1.42 秒降至 1.25 秒",
    progress: {
      previous: 1.58,
      current: 1.42,
      target: 1.25,
      unit: "秒",
    },
  },
];

export const hardwarePreview: HardwarePreview = {
  phaseLabel: productCopy.hardware.title,
  disclaimer: productCopy.hardware.disclaimer,
  metrics: [
    {
      id: "sweet",
      label: "甜区命中率",
      value: "74%",
      detail: "TENG 3x3 阵列模拟输出",
    },
    {
      id: "impact",
      label: "握持力度",
      value: "8.2 N*",
      detail: "由电压幅值映射的演示值",
    },
    {
      id: "swing",
      label: "挥拍速度",
      value: "21.4 m/s",
      detail: "IMU 角速度与线加速度融合",
    },
    {
      id: "quality",
      label: "动作质量",
      value: "88",
      detail: "甜区、速度、角度综合评分",
    },
  ],
  sweetZone: [
    { id: "z1", row: 1, col: 1, intensity: 0.28 },
    { id: "z2", row: 1, col: 2, intensity: 0.48 },
    { id: "z3", row: 1, col: 3, intensity: 0.22 },
    { id: "z4", row: 2, col: 1, intensity: 0.52 },
    { id: "z5", row: 2, col: 2, intensity: 0.95 },
    { id: "z6", row: 2, col: 3, intensity: 0.62 },
    { id: "z7", row: 3, col: 1, intensity: 0.18 },
    { id: "z8", row: 3, col: 2, intensity: 0.44 },
    { id: "z9", row: 3, col: 3, intensity: 0.31 },
  ],
  highlightedCellId: "z5",
  fusionPoints: [
    {
      visual: "人员移动覆盖到右侧后场",
      sensor: "甜区中心偏右命中，力度峰值稳定",
      insight: "该段移动质量高，可作为后续位移投影模板。",
    },
    {
      visual: "反手侧处理后移动路径绕行",
      sensor: "挥拍末段角速度下降",
      insight: "需要先恢复支撑姿态，再追求反手深度。",
    },
  ],
};

export const platformNavigation: NavigationItem[] = [
  { id: "home", label: "首页", shortLabel: "首页", path: "/" },
];

export const matchSummary: MatchSummary = {
  title: "北京体育大学训练场对局样本",
  subtitle: "智能比赛分析 · 双打训练样本",
  date: "2026-05-04",
  venue: "北京体育大学匹克球训练场",
  teams: "荧光队 对阵 蓝队",
  score: "11 - 8",
  currentRally: "移动轨迹样本",
  currentTime: "08:42",
  duration: "12:16",
};

export const overviewCards: OverviewCard[] = [
  {
    id: "vision",
    title: "上传比赛分析",
    body: "从视频上传、场地标定到任务生成，按真实分析流程启动一场复盘。",
    path: "/analysis/new",
    metric: "创建新任务",
  },
  {
    id: "tasks",
    title: "分析任务管理",
    body: "查看所有历史和正在运行的分析任务，完成后进入纯净视频结果页。",
    path: "/analysis/tasks",
    metric: "任务状态追踪",
  },
  {
    id: "training",
    title: "训练建议闭环",
    body: "把弱项转成下一次训练任务，而不是停留在一个分数。",
    path: "/training",
    metric: "4 项训练待练",
  },
  {
    id: "demo",
    title: "演示工作台",
    body: "保留样例视频分析，用于无后端或演示场景快速展示视觉效果。",
    path: "/vision",
    metric: "样例数据",
  },
];

export const playerMarkers: PlayerMarker[] = [
  { id: "a", label: "A", team: "near", x: 28, y: 72, color: "#22C55E" },
  { id: "b", label: "B", team: "near", x: 68, y: 76, color: "#D9FF3F" },
  { id: "c", label: "C", team: "far", x: 34, y: 23, color: "#2F80ED" },
  { id: "d", label: "D", team: "far", x: 75, y: 28, color: "#FF9500" },
];

export const videoOverlayLabels: VideoOverlayLabel[] = [
  { id: "movement", label: "人员移动轨迹", tone: "training", x: 54, y: 42 },
  { id: "coverage", label: "右侧覆盖偏慢", tone: "risk", x: 39, y: 31 },
  { id: "recovery", label: "回位路径绕行", tone: "error", x: 63, y: 47 },
  { id: "projection", label: "投影底图预留", tone: "advantage", x: 72, y: 24 },
];

export const timelineMarkers: TimelineMarker[] = [
  { id: "calibration", time: "00:12", position: 9, label: "场地标定完成", tone: "advantage" },
  { id: "right-coverage", time: "02:44", position: 28, label: "右侧覆盖后回位偏慢", tone: "risk" },
  { id: "recovery", time: "06:18", position: 56, label: "回位路径出现绕行", tone: "error" },
  { id: "summary", time: "08:42", position: 76, label: "移动覆盖摘要", tone: "advantage" },
];

export const highlights: Highlight[] = [
  {
    id: "h1",
    title: "移动覆盖摘要",
    time: "08:42",
    result: "轨迹样例",
    tone: "advantage",
    description: "人员轨迹集中在中后场，适合作为后续标准球场投影的演示入口。",
  },
  {
    id: "h2",
    title: "右侧覆盖段",
    time: "06:18",
    result: "回位偏慢",
    tone: "error",
    description: "右侧覆盖后恢复路径偏长，后续可用人员位移数据持续验证。",
  },
  {
    id: "h3",
    title: "启动节奏 #09",
    time: "02:44",
    result: "启动延迟",
    tone: "risk",
    description: "从静止到横移的第一步略慢，适合纳入移动训练重点。",
  },
  {
    id: "h4",
    title: "覆盖平衡 #12",
    time: "04:05",
    result: "左右均衡",
    tone: "training",
    description: "左右覆盖比例接近均衡，可作为标准场地投影的参考样本。",
  },
];

export const coachNotes: CoachNote[] = [
  {
    id: "note-advantage",
    tone: "advantage",
    title: "覆盖平衡接近理想",
    body: "样例移动路径显示左右覆盖较均衡，可作为后续人员位移投影的展示基线。",
  },
  {
    id: "note-risk",
    tone: "risk",
    title: "右侧回位仍有延迟",
    body: "右侧覆盖后的恢复路径偏长，适合用移动轨迹和速度指标继续验证。",
  },
  {
    id: "note-error",
    tone: "error",
    title: "连续移动后的稳定性下降",
    body: "连续移动进入后段时，回位路径更容易绕行，建议先优化第一步启动。",
  },
  {
    id: "note-training",
    tone: "training",
    title: "建议训练重点",
    body: "建议训练：右侧横移回位 + 分腿垫步启动，先稳定移动节奏再提高速度。",
  },
];

export const reportActions: ReportAction[] = [
  {
    type: "performance",
    title: "本场表现报告",
    description: "总结优势与首要问题，并转化为下一次训练目标。",
    path: "/reports/performance",
  },
  {
    type: "movement",
    title: "步法移动报告",
    description: "拆解回位路径、覆盖平衡和启动延迟。",
    path: "/reports/movement",
  },
  {
    type: "diagnosis",
    title: "动作诊断报告",
    description: "把动作问题转成证据和纠正方向。",
    path: "/reports/diagnosis",
  },
];

export const dashboardMetrics: DashboardMetric[] = [
  {
    id: "overall",
    icon: "activity",
    label: "综合表现评分",
    value: "82",
    detail: "移动覆盖抵消了后段网前失误",
    trend: "较上场 +8%",
    direction: "up",
    progress: 82,
    sparkline: [62, 66, 70, 68, 74, 82],
  },
  {
    id: "serve",
    icon: "target",
    label: "起始站位稳定",
    value: "87%",
    detail: "准备位和启动方向稳定可靠",
    trend: "+4%",
    direction: "up",
    progress: 87,
    sparkline: [74, 78, 76, 82, 84, 87],
  },
  {
    id: "return",
    icon: "send",
    label: "回位深度评分",
    value: "74",
    detail: "反手侧覆盖后仍能回到中线附近",
    trend: "+12",
    direction: "up",
    progress: 74,
    sparkline: [52, 58, 61, 64, 68, 74],
  },
  {
    id: "third",
    icon: "waves",
    label: "回位效率",
    value: "61%",
    detail: "右侧覆盖后的回位仍偏慢",
    trend: "-3%",
    direction: "down",
    progress: 61,
    sparkline: [66, 68, 64, 65, 63, 61],
  },
  {
    id: "dink",
    icon: "shield",
    label: "网前站位稳定",
    value: "58%",
    detail: "连续移动后站位波动上升",
    trend: "+2%",
    direction: "steady",
    progress: 58,
    sparkline: [54, 55, 57, 56, 59, 58],
  },
  {
    id: "errors",
    icon: "alert",
    label: "非受迫失误",
    value: "14",
    detail: "其中 9 次来自网前和过渡区",
    trend: "较上场 -5",
    direction: "up",
    progress: 66,
    sparkline: [22, 21, 19, 18, 16, 14],
  },
  {
    id: "kitchen",
    icon: "radar",
    label: "网前区域控制",
    value: "68%",
    detail: "站位合理，手感质量仍可提升",
    trend: "+6%",
    direction: "up",
    progress: 68,
    sparkline: [49, 54, 58, 61, 63, 68],
  },
  {
    id: "rally-length",
    icon: "timer",
    label: "连续移动长度",
    value: "9.6 段",
    detail: "连续移动暴露反手侧回位短板",
    trend: "+1.4",
    direction: "up",
    progress: 72,
    sparkline: [6.8, 7.2, 7.6, 8.1, 8.9, 9.6],
  },
];

export const skillRatings: SkillRating[] = [
  {
    id: "serve-pressure",
    label: "起始站位",
    score: 82,
    note: "准备位稳定，能让后续移动启动更顺畅。",
  },
  {
    id: "return-quality",
    label: "回位质量",
    score: 74,
    note: "样例保留为训练占位，真实任务暂不输出战术质量。",
  },
  {
    id: "third-shot",
    label: "右侧回位",
    score: 61,
    note: "右侧覆盖后的恢复路径仍可优化。",
  },
  {
    id: "kitchen-control",
    label: "网前控制",
    score: 68,
    note: "站位不错，连续移动后节奏波动。",
  },
  {
    id: "defensive-reset",
    label: "防守重置",
    score: 73,
    note: "过渡区处理有效，但回位路径偏长。",
  },
  {
    id: "decision-making",
    label: "决策选择",
    score: 79,
    note: "能识别变线机会，少数强攻时机偏早。",
  },
];

export const drillRecommendations: DrillRecommendation[] = [
  {
    id: "drill-backhand-dink",
    title: "反手侧移动稳定性",
    goal: "连续 30 次反手侧横移后回到标准准备位。",
    duration: "18 分钟",
    evidence: "样例显示连续移动后反手侧回位路径更容易绕行。",
    difficulty: "进阶",
    linkedReport: "diagnosis",
  },
  {
    id: "drill-third-shot",
    title: "右侧覆盖后回位节奏",
    goal: "右侧横移后快速恢复到中线附近，完成 4 组。",
    duration: "22 分钟",
    evidence: "样例移动路径显示右侧覆盖后的恢复路径偏长。",
    difficulty: "高级",
    linkedReport: "movement",
  },
  {
    id: "drill-return-depth",
    title: "反手侧回位覆盖",
    goal: "从反手侧移动后回到标准准备位，覆盖率保持 70% 以上。",
    duration: "15 分钟",
    evidence: "样例覆盖数据提示反手侧恢复仍有提升空间。",
    difficulty: "基础",
    linkedReport: "movement",
  },
  {
    id: "drill-transition-reset",
    title: "过渡区重置",
    goal: "从中场低位恢复到厨房区附近，减少无效绕行。",
    duration: "20 分钟",
    evidence: "过渡区移动路径有 3 次明显绕行。",
    difficulty: "进阶",
    linkedReport: "movement",
  },
];

export const progressPoints: ProgressPoint[] = [
  { match: "第1场", performance: 67, errors: 23, thirdShot: 48, kitchen: 52 },
  { match: "第2场", performance: 71, errors: 20, thirdShot: 55, kitchen: 57 },
  { match: "第3场", performance: 73, errors: 19, thirdShot: 58, kitchen: 60 },
  { match: "第4场", performance: 78, errors: 16, thirdShot: 64, kitchen: 63 },
  { match: "第5场", performance: 82, errors: 14, thirdShot: 61, kitchen: 68 },
];

const reportMetricMap: Record<ReportDefinition["type"], DashboardMetric[]> = {
  movement: dashboardMetrics.filter((metric) => ["overall", "kitchen", "rally-length", "errors"].includes(metric.id)),
  diagnosis: dashboardMetrics.filter((metric) => ["errors", "third", "dink", "overall"].includes(metric.id)),
};

export const reportDefinitions: ReportDefinition[] = [
  {
    type: "movement",
    title: "移动与覆盖平衡报告",
    eyebrow: "步法移动报告",
    summary: "覆盖平衡接近理想，但反手回球后的恢复路径多出 2 次绕行。",
    heroMetric: "48 / 52",
    heroMetricLabel: "左右覆盖平衡",
    visualization: "movement",
    metrics: reportMetricMap.movement,
    insights: [
      {
        id: "movement-1",
        tone: "risk",
        title: "回位路径是隐藏消耗",
        body: "反手回球后多绕行 0.6m，下一拍启动慢，容易被中路压迫。",
      },
      coachNotes[3],
    ],
    trainingLink: "过渡区重置",
  },
  {
    type: "diagnosis",
    title: "动作诊断报告",
    eyebrow: "动作诊断报告",
    summary: "主要问题来自反手准备节奏和连续移动后的重心控制，训练要先稳定姿态和脚步。",
    heroMetric: "3",
    heroMetricLabel: "已识别优先问题",
    visualization: "diagnosis",
    metrics: reportMetricMap.diagnosis,
    insights: [coachNotes[2], coachNotes[3]],
    trainingLink: "反手侧移动稳定性",
  },
];

export const demoAnalysisReport: AnalysisReport = {
  version: "analysis-report-v1",
  source: "demo",
  reportId: reportSession.reportId,
  generatedAt: "2026-05-04T12:30:00+08:00",
  metadata: {
    fileName: "demo-pickleball-match.mp4",
    fileSize: 248_000_000,
    matchTitle: matchSummary.title,
    venue: reportSession.venue,
    matchDate: reportSession.date,
    matchFormat: "doubles",
    cameraAngle: "elevated",
    athleteLabel: reportSession.athlete,
    level: reportSession.level,
  },
  match: matchSummary,
  session: reportSession,
  dashboardMetrics,
  reportDefinitions,
  reportActions,
  playerMarkers,
  shotTrajectories: [],
  videoOverlayLabels,
  timelineMarkers,
  highlights,
  coachNotes,
  diagnoses,
  trainingRecommendations,
  drillRecommendations,
  shotRows: [],
  skillRatings,
  progressPoints,
};
