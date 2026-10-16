import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  applyTheme,
  persistTheme,
  readStoredTheme,
  resolveInitialTheme,
  THEME_STORAGE_KEY,
  isThemeMode,
  DEFAULT_THEME,
  type ThemeMode,
} from "./theme";

interface ThemeContextValue {
  theme: ThemeMode;
  /** 直接设置主题（幂等）。 */
  setTheme: (mode: ThemeMode) => void;
  /** 在亮/暗之间切换。 */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * 主题状态容器。
 *
 * - 初始值与 `index.html` 启动脚本写入的 `data-theme` 同源，避免刷新闪屏；
 * - 切换后同步 DOM、localStorage，并广播自定义事件供同页其他入口同步；
 * - 监听 `storage` 事件以跟随同源其他标签页的选择。
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => resolveInitialTheme());

  const previousThemeRef = useRef(theme);
  const animateNextChangeRef = useRef(false);

  // 状态更新器必须保持纯函数；DOM、存储与事件在提交后同步，避免
  // StrictMode 重复求值或自定义事件重入导致一次点击切换两次。
  useEffect(() => {
    const changed = previousThemeRef.current !== theme;
    previousThemeRef.current = theme;
    applyTheme(theme, { animate: changed && animateNextChangeRef.current });
    animateNextChangeRef.current = false;
    if (!changed) return;
    persistTheme(theme);
    window.dispatchEvent(new CustomEvent<ThemeMode>("app:themechange", { detail: theme }));
  }, [theme]);

  const setTheme = useCallback((mode: ThemeMode) => {
    animateNextChangeRef.current = previousThemeRef.current !== mode;
    setThemeState(mode);
  }, []);

  const toggleTheme = useCallback(() => {
    animateNextChangeRef.current = true;
    setThemeState((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  // 跨标签页同步：同源其他标签页写入存储时跟随。
  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== null && event.key !== THEME_STORAGE_KEY) return;
      const next = event.newValue ?? readStoredTheme();
      if (!isThemeMode(next)) return;
      setThemeState((current) => (current === next ? current : next));
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  // 同页面其他切换入口同步（后续若新增侧边栏/设置入口可直接派发该事件）。
  useEffect(() => {
    const handleCustom = (event: Event) => {
      const detail = (event as CustomEvent<ThemeMode>).detail;
      if (!isThemeMode(detail)) return;
      setThemeState((current) => (current === detail ? current : detail));
    };
    window.addEventListener("app:themechange", handleCustom);
    return () => window.removeEventListener("app:themechange", handleCustom);
  }, []);

  const value = useMemo<ThemeContextValue>(() => ({ theme, setTheme, toggleTheme }), [theme, setTheme, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** 读取主题状态；在 `ThemeProvider` 之外调用会抛出，便于尽早暴露装配错误。 */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme 必须在 ThemeProvider 内使用");
  return ctx;
}

/** 无 Provider 时的只读回退（亮色），保证组件可被单独渲染/测试。 */
const FALLBACK_CONTEXT: ThemeContextValue = {
  theme: DEFAULT_THEME,
  setTheme: () => {},
  toggleTheme: () => {},
};

/**
 * 与 `useTheme` 相同，但在 `ThemeProvider` 之外回退到亮色的空操作实现。
 * 供图表等可能被独立挂载的组件使用，避免测试环境缺少 Provider 直接崩溃。
 */
export function useThemeOptional(): ThemeContextValue {
  return useContext(ThemeContext) ?? FALLBACK_CONTEXT;
}
