// =============================================================
// 教学助教 Agent —— 首版演示素材
// -------------------------------------------------------------
// 用途：比赛演示阶段，在没有接入大模型时也能完整跑通
//       「读取证据 → 检索练习 → 保存计划 → 连续改写」的交互闭环。
//
// 口径边界（重要，勿扩写）：
//   · 移动距离 / 站位覆盖 / 回位间隔 属系统真实可产出指标；
//   · 击球类型、甜区命中率、战术语义 当前不产出，剧本里必须显式说明不具备；
//   · 所有数字均为演示样例值，界面会标注「演示样例」，不冒充真实任务结果。
//
// 接入真实后端后，本文件整体可删除（client 切换为真实接口即可）。
// =============================================================
import type {
  CoachDrill,
  CoachEvidenceItem,
  CoachPlanStep,
  CoachToolName,
  CoachTrainingPlan,
} from "../types/coachAgent";

/** 首版教学练习库（教师核对过的练习卡，8 条覆盖常见初学问题） */
export const teachingDrills: CoachDrill[] = [
  {
    id: "drill-kitchen-touch",
    name: "厨房线两点触线",
    focus: "回位启动慢、厨房线前脚步发沉",
    minutes: 6,
    groupSize: "1–2 人",
    equipment: "球拍 1 支、球 3 个、标志碟 2 个",
    steps: [
      "以厨房线为基准，左右各放一只标志碟，间距 2.5 米。",
      "球员站在两碟中点，听到口令后侧向滑步触及一侧碟面，立刻回中再触另一侧。",
      "每组 30 秒，组间休息 20 秒；触线瞬间要求膝盖过脚尖、上身不后仰。",
    ],
    target: "30 秒内触线次数 ≥ 14 次，回中到位率 ≥ 80%",
    evidenceIds: ["E3"],
  },
  {
    id: "drill-split-step",
    name: "分腿垫步定格",
    focus: "对手击球瞬间未落地，启动晚半拍",
    minutes: 4,
    groupSize: "1–2 人",
    equipment: "球拍 1 支、球 5 个",
    steps: [
      "搭档在网前抛球，球员在搭档脱手瞬间完成分腿垫步并落地定格 1 秒。",
      "定格确认后再接球，连续 10 球为一组。",
      "进阶：搭档改为随机方向抛球，球员仍须先垫步后移动。",
    ],
    target: "10 球中 ≥ 8 球在球落地前完成垫步落地",
    evidenceIds: ["E3"],
  },
  {
    id: "drill-serve-recover",
    name: "发球后回位",
    focus: "发球后原地观望，第二拍被动",
    minutes: 4,
    groupSize: "2 人",
    equipment: "球拍 2 支、球 6 个",
    steps: [
      "球员发球后必须完成一次向厨房线的前压步，再进入准备位。",
      "搭档回球到任意落点，球员从准备位启动接球。",
      "每 6 球一轮，轮换发球方。",
    ],
    target: "发球后 2 秒内进入准备位比例 ≥ 85%",
    evidenceIds: ["E3"],
  },
  {
    id: "drill-lateral-shuffle",
    name: "侧向滑步折返",
    focus: "横向覆盖不足，双打边线球放弃过早",
    minutes: 5,
    groupSize: "1–4 人",
    equipment: "标志碟 4 个",
    steps: [
      "用标志碟标出 6 米宽通道，球员保持低重心侧向滑步至终点再折返。",
      "往返 2 趟为一组，共 3 组；全程不交叉步。",
      "进阶：搭档随机指方向，球员只做一次变向。",
    ],
    target: "6 米往返用时 ≤ 9 秒且全程不交叉步",
    evidenceIds: ["E1", "E2"],
  },
  {
    id: "drill-partner-feed",
    name: "双人轮转喂球",
    focus: "两人共用一块场地时的组织方式",
    minutes: 4,
    groupSize: "2 人",
    equipment: "球拍 2 支、球 10 个",
    steps: [
      "一人喂球 60 秒、另一人练指定步法，随后交换。",
      "喂球方要求落点稳定在厨房区内，练的人只做步法不发力击球。",
      "两轮交换后合练 1 分钟对拍。",
    ],
    target: "每轮喂球成功 ≥ 12 个，练的人回中率 ≥ 80%",
    evidenceIds: ["E3"],
  },
  {
    id: "drill-third-shot",
    name: "第三拍放小球 + 上前",
    focus: "第三拍过渡球过高，被对方压制",
    minutes: 6,
    groupSize: "2–4 人",
    equipment: "球拍 2 支、球 8 个",
    steps: [
      "从底线发球，接发方回深球，球员第三拍必须放至厨房区。",
      "放球成功后立即上前两步，进入厨房线准备位。",
      "10 球为一组，记录成功入区数量。",
    ],
    target: "10 球中 ≥ 6 球落入厨房区且完成上前",
    evidenceIds: ["E2"],
  },
  {
    id: "drill-fast-hands",
    name: "网前快速对拍",
    focus: "厨房线对拍节奏跟不上，拍面控制不稳",
    minutes: 3,
    groupSize: "2 人",
    equipment: "球拍 2 支、球 4 个",
    steps: [
      "两人站在厨房线后 1 米，只允许轻挡不发力。",
      "连续对拍 20 拍为一组，失误即重新计数。",
      "要求拍面始终在胸前高度，不后拉。",
    ],
    target: "单组连续对拍 ≥ 15 拍",
    evidenceIds: [],
  },
  {
    id: "drill-deep-retreat",
    name: "深区退防",
    focus: "被压底线时后退步混乱、失去平衡",
    minutes: 4,
    groupSize: "2 人",
    equipment: "球拍 2 支、球 6 个",
    steps: [
      "搭档送高远球到头顶后方，球员交叉步后退击球后立即回位。",
      "每次击球后必须回到中场标记点。",
      "6 球一轮，注意后退时不回头看球。",
    ],
    target: "6 球中 ≥ 4 球完成击球后回位到中场",
    evidenceIds: ["E1"],
  },
];

/** 演示用证据（数值为样例，界面标注「演示样例」） */
export const demoEvidence: CoachEvidenceItem[] = [
  {
    id: "E1",
    metric: "累计移动距离",
    value: "186 ft",
    detail: "单场累计 · 轨迹连续段占比 78%",
    quality: "medium",
    windowLabel: "01:12–01:48",
  },
  {
    id: "E2",
    metric: "前场停留占比",
    value: "21%",
    detail: "厨房区停留 / 总有效移动时间",
    quality: "medium",
    windowLabel: "01:12–01:48",
  },
  {
    id: "E3",
    metric: "回位启动间隔",
    value: "8.4 s",
    detail: "两次横向补位之间的平均间隔",
    quality: "low",
    windowLabel: "02:14–02:19",
  },
  {
    id: "E4",
    metric: "有效移动时间",
    value: "4 分 12 秒",
    detail: "剔除静止与出画片段后的时长",
    quality: "high",
  },
];

function step(
  id: string,
  title: string,
  minutes: number,
  note: string,
  drillId: string,
  evidenceIds: string[] = []
): CoachPlanStep {
  return { id, title, minutes, note, drillId, evidenceIds };
}

/** 场景 2：15 分钟单人步法计划（v1 基线） */
const plan15: CoachTrainingPlan = {
  version: 1,
  goal: "提高回位启动速度，把厨房区停留占比从 21% 提到 30% 以上",
  level: "初学",
  totalMinutes: 15,
  groupSize: "1 人",
  steps: [
    step("s1", "热身：分腿垫步 + 侧向滑步", 3, "先唤醒启动动作，不追求强度", "drill-split-step"),
    step("s2", "主练：厨房线两点触线", 6, "直接对应 E3 回位启动间隔偏长", "drill-kitchen-touch", ["E3"]),
    step("s3", "组合：发球后回位", 4, "把步法放回真实回合情境", "drill-serve-recover", ["E3"]),
    step("s4", "收尾：30 秒复测", 2, "当场取一次数据，作为下次对照基线", "drill-kitchen-touch", ["E3"]),
  ],
  reassess: ["回位启动间隔 ≤ 6.0 s（当前 8.4 s）", "厨房区停留占比 ≥ 30%（当前 21%）"],
  evidenceIds: ["E1", "E2", "E3"],
  savedAt: "2026-11-10T21:30:00+08:00",
  status: "saved",
};

/** 场景 3：压缩到 8 分钟、两人一组的 v2 */
const plan8: CoachTrainingPlan = {
  version: 2,
  goal: "在 8 分钟内保持同一训练目标：回位启动更快、前场站位更主动",
  level: "初学",
  totalMinutes: 8,
  groupSize: "2 人（轮转）",
  steps: [
    step("s1", "双人轮转喂球（热身兼主练）", 4, "一人喂球 60 秒、一人做两点触线，两轮后交换", "drill-partner-feed", ["E3"]),
    step("s2", "发球后回位（对拍形式）", 3, "保留真实回合情境，两人互为发球方", "drill-serve-recover", ["E3"]),
    step("s3", "两人同时复测 30 秒", 1, "各自记录触线次数，当场对照", "drill-kitchen-touch", ["E3"]),
  ],
  reassess: ["8 分钟内可测：回位启动间隔 ≤ 7.0 s（放宽自 6.0 s）", "两人触线次数差 ≤ 2 次，便于同场比较"],
  evidenceIds: ["E1", "E2", "E3"],
  savedAt: "2026-11-10T21:34:00+08:00",
  status: "saved",
};

export interface CoachDemoToolSpec {
  name: CoachToolName;
  title: string;
  argument: string;
  result: string;
}

export interface CoachDemoScene {
  id: string;
  /** 快捷问题（首屏完整问句，录演示时直接点，保证顺序稳定） */
  chip: string;
  /** 对话开始后的紧凑标签（同一问题，短文案） */
  shortChip: string;
  match: RegExp;
  tools: CoachDemoToolSpec[];
  /** 回答正文，支持 {{player}} 占位 */
  answer: string;
  /** 无上一版计划时的替代回答（场景 3 用） */
  answerWithoutPlan?: string;
  evidence?: CoachEvidenceItem[];
  plan?: CoachTrainingPlan;
  limitation?: string;
}

const EVIDENCE_TOOL: CoachDemoToolSpec = {
  name: "get_analysis_evidence",
  title: "读取分析证据",
  argument: "scope=本次任务 · subject={{player}} · 只要可核对的指标",
  result: "返回 4 条可用证据（移动 2 · 站位 1 · 质量 1），1 项维度标记为数据不足",
};

export const coachDemoScenes: CoachDemoScene[] = [
  {
    id: "explain-movement",
    chip: "解释这位球员的移动数据，列出依据",
    shortChip: "解释移动数据",
    match: /(解释|说明|为什么|移动|跑动|距离|数据|依据|指标)/,
    tools: [EVIDENCE_TOOL],
    answer:
      "{{player}} 本场累计移动 186 英尺（约 57 米），有效移动时间 4 分 12 秒，折合平均移动速度约 0.74 英尺/秒。\n\n从这三条能对上的依据看：E1 移动总量不算低，说明覆盖范围不是主要问题；E2 前场（厨房区）停留只占 21%，明显偏少；E3 两次横向补位之间的平均间隔 8.4 秒，回位启动偏慢。\n\n所以更可能的症结是「打完后不回中、二次启动慢」，而不是「跑不动」。E3 的质量标记是低，样本只有 6 次，如果要写进训练目标，建议先看 02:14–02:19 这段回放确认一次。",
    evidence: demoEvidence,
  },
  {
    id: "plan-15min",
    chip: "给这位初学者安排 15 分钟步法练习",
    shortChip: "15 分钟步法计划",
    match: /(15\s*分钟|十五分钟|步法|初学者|初学|安排|计划|练习)/,
    tools: [
      EVIDENCE_TOOL,
      {
        name: "find_teaching_drills",
        title: "检索教学练习",
        argument: "focus=回位启动 · level=初学 · group=1 · minutes=15",
        result: "命中 3 条练习（步法 2 · 组合 1），均已按「回位启动」标注适用性",
      },
      {
        name: "save_training_plan",
        title: "保存训练计划",
        argument: "steps=4 · total=15 min · evidence=E1,E2,E3",
        result: "计划 v1 已保存（草稿，可继续改写）",
      },
    ],
    answer:
      "按 15 分钟、单人、初学来排，我选了三段递进：先唤醒启动动作，再针对性练回位，最后放回真实回合里验证。\n\n顺序有讲究——E3 显示的是「补位后回不来」，所以主练必须紧接热身，趁动作还没凉；发球后回位放在第三段，是为了把练出来的启动放回情境里，而不是只做无球的空跑。\n\n整套 15 分钟，练完当场测一次 30 秒触线，作为下次对照的基线。计划已存为 v1，随时可以改时长和人数。",
    evidence: demoEvidence,
    plan: plan15,
  },
  {
    id: "adjust-8min-two",
    chip: "只有 8 分钟，而且是两个人一起练",
    shortChip: "改成 8 分钟两人",
    match: /(8\s*分钟|八分钟|两个人|两人|两人一组|改|压缩|缩短|一起练)/,
    tools: [
      {
        name: "save_training_plan",
        title: "保存训练计划",
        argument: "revise from v1 · total=8 min · group=2 · 保留原目标与证据",
        result: "计划 v2 已保存（目标不变 · 组织方式改为双人轮转）",
      },
    ],
    answer:
      "改成 8 分钟、两人一组，我保留了原目标（回位启动更快、前场站位更主动）和全部证据引用，只动三件事：\n\n第一，把「热身 + 主练」合成一段双人轮转——一人喂球 60 秒、一人做触线，两轮后交换，热身和主练一次完成。第二，砍掉单独的发球后回位段，改成对拍形式，两个人互为发球方，照样能练到启动。第三，复测从 2 分钟压到 1 分钟，两人同时测，方便同场比较。\n\n代价要说清楚：8 分钟没法同时保证练习量和复测精度，所以复测阈值从 6.0 秒放宽到 7.0 秒。这是取舍，不是能力提升。",
    answerWithoutPlan:
      "当前还没有上一版计划，我直接按 8 分钟、两人一组排一版。\n\n组织方式用双人轮转：一人喂球 60 秒、一人做厨房线两点触线，两轮后交换，热身和主练一次完成；第二段改成对拍形式的发球后回位，两人互为发球方，照样能练到启动；最后 1 分钟两人同时测 30 秒触线，方便同场比较。\n\n8 分钟无法同时保证练习量和复测精度，所以复测阈值放宽到 7.0 秒。这是取舍，不是能力提升。",
    evidence: demoEvidence,
    plan: plan8,
  },
  {
    id: "sweet-spot-limit",
    chip: "判断他的甜区命中率是多少",
    shortChip: "甜区命中率怎么算",
    match: /(甜区|命中率|击球点|拍面|sweet)/,
    tools: [
      {
        name: "get_analysis_evidence",
        title: "读取分析证据",
        argument: "requested=sweet_spot_hit_rate · subject={{player}}",
        result: "该维度无可用产物：当前分析不含球拍击球点与甜区定位",
      },
    ],
    answer:
      "这项我判断不了，也不能给你一个看起来合理的数字。\n\n原因很具体：当前分析链路的产物是人员检测、姿态、轨迹投影和移动指标，没有球拍击球点定位，也没有球与拍面的接触时刻，所以「甜区命中率」缺少分子和分母。这是采集侧的限制——没有拍面传感器，球追踪也还不是正式输出。\n\n能替代的、且能对得上的指标有三个：进区率、落点分布、以及击球后的回位间隔。如果你要评估「击球质量」，建议先用「进区率 + 落点深度分布」这两项，它们是本次任务真实可读的。",
    evidence: demoEvidence.slice(3),
    limitation: "该维度当前无真实数据，不做推测",
  },
];

/** 未命中剧本时的兜底回答（演示版只覆盖四类问题） */
export const coachFallbackAnswer =
  "演示版目前覆盖四类问题：解释移动数据、生成 15 分钟步法练习、把计划改成 8 分钟双人、以及说明哪些指标当前判断不了。\n\n接入真实模型后，这里会直接基于本次任务的全部证据作答。你可以先点上面的示例问题，看一下工具调用和计划改写的完整过程。";
