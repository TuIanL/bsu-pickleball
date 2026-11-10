// =============================================================
// 教学助教 Agent —— 前端契约
// -------------------------------------------------------------
// 这一层只描述「界面需要什么」，不绑定具体模型供应商。
// 未来接入真实后端时，后端返回同构 JSON 即可替换 services/coachAgentClient.ts。
// =============================================================

/** Agent 可调用的工具（与后端工具定义同名，便于日志对齐） */
export type CoachToolName =
  | "get_analysis_evidence"
  | "find_teaching_drills"
  | "save_training_plan";

export type CoachToolStatus = "running" | "done" | "failed";

/** 一次工具调用（用于把 Agent 的取数过程显式展示给教师/评委） */
export interface CoachToolCall {
  id: string;
  name: CoachToolName;
  /** 中文短标签，如「读取分析证据」 */
  title: string;
  /** 参数摘要，一行 */
  argument: string;
  /** 结果摘要，一行；running 时为空 */
  result: string;
  status: CoachToolStatus;
}

export type CoachEvidenceQuality = "high" | "medium" | "low";

/** 可被回答引用的证据条目（编号 + 指标 + 质量 + 可选回放窗口） */
export interface CoachEvidenceItem {
  /** 证据编号，回答中以 [E1] 形式引用 */
  id: string;
  metric: string;
  value: string;
  /** 口径/来源说明，如「单场累计 · 轨迹连续段 78%」 */
  detail: string;
  quality: CoachEvidenceQuality;
  /** 关联的表现洞察 finding id（真实报告存在时） */
  findingId?: string;
  /** 可回放窗口，如「02:14–02:19」；无窗口时留空，不编造时间点 */
  windowLabel?: string;
}

/** 教学练习卡（首版为教师核对过的小型练习库） */
export interface CoachDrill {
  id: string;
  name: string;
  /** 针对的问题，如「回位启动慢」 */
  focus: string;
  minutes: number;
  groupSize: string;
  equipment: string;
  steps: string[];
  /** 可复测指标 */
  target: string;
  evidenceIds: string[];
}

/** 计划中的一步 */
export interface CoachPlanStep {
  id: string;
  title: string;
  minutes: number;
  note: string;
  drillId?: string;
  evidenceIds: string[];
}

/** 训练计划（首版为带版本的 JSON 草稿，暂不落库） */
export interface CoachTrainingPlan {
  version: number;
  goal: string;
  level: string;
  totalMinutes: number;
  groupSize: string;
  steps: CoachPlanStep[];
  /** 复测指标：下次训练前如何验证 */
  reassess: string[];
  evidenceIds: string[];
  savedAt: string;
  status: "draft" | "saved";
}

export interface CoachMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** 该条回答触发的工具调用 */
  toolCalls?: CoachToolCall[];
  /** 该条回答引用的证据 */
  evidence?: CoachEvidenceItem[];
  /** 该条回答是否更新了计划，及更新后的版本号 */
  planVersion?: number;
  /** 数据不足时给出的边界说明 */
  limitation?: string | null;
  /** 是否仍在流式输出 */
  streaming?: boolean;
}

/** 面板顶部展示的分析上下文（全部来自当前报告，不编造） */
export interface CoachContext {
  /** 任务标题或样例标识 */
  taskLabel: string;
  playerLabel: string;
  /** 数据来源：真实 job / 演示样例 */
  source: "job" | "demo";
  /** 质量一句话说明 */
  dataQuality: string;
  /** 可用证据条目 */
  evidence: CoachEvidenceItem[];
  /** 当前报告是否真的具备表现洞察 */
  hasInsights: boolean;
}

/** 一次提问的请求（未来即后端 /api/coach/chat 的 body） */
export interface CoachTurnRequest {
  message: string;
  context: CoachContext;
  plan: CoachTrainingPlan | null;
  /** 之前的用户消息，用于多轮改写 */
  history: Array<{ role: "user" | "assistant"; text: string }>;
}

/** 流式事件：工具调用 / 文本增量 / 证据 / 计划更新 */
export type CoachStreamEvent =
  | { type: "tool_start"; call: CoachToolCall }
  | { type: "tool_done"; id: string; result: string; status?: CoachToolStatus }
  | { type: "text_delta"; delta: string }
  | { type: "evidence"; items: CoachEvidenceItem[] }
  | { type: "plan"; plan: CoachTrainingPlan }
  | { type: "limitation"; text: string }
  | { type: "error"; message: string };
