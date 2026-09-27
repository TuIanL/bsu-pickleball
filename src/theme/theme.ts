/**
 * 界面主题（`light` / `dark`）的状态来源、持久化与 DOM 落地。
 *
 * 约定：
 * - `<html data-theme="...">` 是主题的唯一 DOM 标记，CSS 与启动脚本都读它；
 * - `localStorage` 只接受 `light` / `dark` 两个值，任何异常都回退到亮色；
 * - React 状态与 DOM 标记保持同源，避免两份状态互相打架。
 */

export type ThemeMode = "light" | "dark";

/** 主题存储键；`index.html` 的启动脚本使用同一个键，修改需同步。 */
export const THEME_STORAGE_KEY = "pre-pickleball.theme";

/** 首次访问或存储无效时的主题：恒为亮色，不跟随系统偏好。 */
export const DEFAULT_THEME: ThemeMode = "light";

/** 切换瞬间挂到 `<html>` 的过渡类名，用于产生自然的明暗过渡。 */
const TRANSITION_CLASS = "theme-transition";
const TRANSITION_DURATION_MS = 180;

/**
 * 过渡的节点数上限。超过该规模时改为瞬时切换：
 * 过渡要求浏览器为每个节点重算样式并重绘颜色，节点上千时整页重绘的代价
 * 会明显高于过渡带来的观感收益，表现为点击切换时的卡顿。
 * 想在所有页面都保留过渡，把这个值调大即可。
 */
const TRANSITION_NODE_BUDGET = 2500;

let transitionTimer: ReturnType<typeof setTimeout> | null = null;

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === "light" || value === "dark";
}

/** 读取存储中的主题；值无效或存储不可用时返回 `null`。 */
export function readStoredTheme(): ThemeMode | null {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeMode(raw) ? raw : null;
  } catch {
    return null;
  }
}

/**
 * 写入主题；存储不可用（隐私模式、配额、被禁用）时静默失败，
 * 仅牺牲跨会话持久化，本页切换仍然有效。
 */
export function persistTheme(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* 存储不可用：忽略 */
  }
}

/**
 * React 初始化时的主题：优先采用启动脚本已写入的 `data-theme`，
 * 缺失时（例如测试环境未执行启动脚本）回退到存储值，再回退到亮色。
 */
export function resolveInitialTheme(): ThemeMode {
  const attr = typeof document === "undefined" ? undefined : document.documentElement.dataset.theme;
  if (isThemeMode(attr)) return attr;
  return readStoredTheme() ?? DEFAULT_THEME;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** 当前文档的元素规模是否还适合跑整页过渡。 */
function isWithinTransitionBudget(): boolean {
  if (typeof document === "undefined") return false;
  return document.querySelectorAll("*").length <= TRANSITION_NODE_BUDGET;
}

/**
 * 将主题落到 DOM。`animate` 仅在用户主动切换时开启，
 * 初始化与跨标签同步不做过渡动画；系统开启“减少动态效果”时不加过渡。
 *
 * 摘类时刻（TRANSITION_DURATION_MS = 180ms）刻意略长于 CSS 中的 140ms，
 * 确保过渡跑完再移除，避免元素停在中间色。
 */
export function applyTheme(mode: ThemeMode, options: { animate?: boolean } = {}): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const changed = root.dataset.theme !== mode;

  if (options.animate && changed && !prefersReducedMotion() && isWithinTransitionBudget()) {
    root.classList.add(TRANSITION_CLASS);
    if (transitionTimer !== null) clearTimeout(transitionTimer);
    transitionTimer = setTimeout(() => {
      root.classList.remove(TRANSITION_CLASS);
      transitionTimer = null;
    }, TRANSITION_DURATION_MS);
  }

  root.dataset.theme = mode;
}
