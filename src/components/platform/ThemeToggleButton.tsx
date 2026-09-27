import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../theme/ThemeProvider";

type ToggleVariant = "header" | "floating";

interface ThemeToggleButtonProps {
  /**
   * `header`：落在 landing 顶栏右侧按钮组中。
   * `floating`：固定在主区域右上角，供 standard / capture 布局使用。
   */
  variant?: ToggleVariant;
  className?: string;
}

const BASE_CLASSES =
  "inline-flex items-center justify-center shrink-0 rounded-full border transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ui-brand)]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ui-surface-page)] disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT_CLASSES: Record<ToggleVariant, string> = {
  header: "size-10",
  floating: "fixed right-4 top-4 z-[60] size-10 shadow-[var(--ui-shadow-card)] backdrop-blur sm:right-6 sm:top-5",
};

/**
 * 月亮／太阳主题切换按钮。
 *
 * 图标表示“点击后将切换到的模式”：亮色下显示月亮（点一下进入暗色），
 * 暗色下显示太阳（点一下回到亮色）；可访问名称同步说明目标模式。
 */
export function ThemeToggleButton({ variant = "header", className }: ThemeToggleButtonProps) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "切换到亮色模式" : "切换到暗色模式";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      data-theme-toggle="true"
      data-theme-mode={theme}
      className={[
        BASE_CLASSES,
        VARIANT_CLASSES[variant],
        "border-[var(--ui-border)] bg-[var(--ui-surface)] text-[var(--ui-text-secondary)]",
        "hover:border-[var(--ui-brand)]/50 hover:text-[var(--ui-brand-deep)]",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  );
}
