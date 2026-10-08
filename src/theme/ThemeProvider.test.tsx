import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeToggleButton } from "../components/platform/ThemeToggleButton";
import { ThemeProvider, useTheme } from "./ThemeProvider";
import { THEME_STORAGE_KEY } from "./theme";

function ThemeProbe() {
  const { theme, setTheme } = useTheme();
  return (
    <>
      <output aria-label="当前主题">{theme}</output>
      <button onClick={() => setTheme("dark")}>选择暗色</button>
      <ThemeToggleButton />
    </>
  );
}

function renderTheme() {
  return render(<StrictMode><ThemeProvider><ThemeProbe /></ThemeProvider></StrictMode>);
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.dataset.theme = "light";
  });

  afterEach(() => {
    cleanup();
    document.documentElement.classList.remove("theme-transition");
    document.documentElement.dataset.theme = "light";
    window.localStorage.clear();
  });

  it("StrictMode 下每次点击只切换一次，并同步按钮、DOM 与存储", () => {
    renderTheme();
    fireEvent.click(screen.getByRole("button", { name: "切换到暗色模式" }));
    expect(screen.getByLabelText("当前主题").textContent).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "切换到亮色模式" }));
    expect(screen.getByLabelText("当前主题").textContent).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("直接设置主题幂等，重新挂载后保留选择", () => {
    const view = renderTheme();
    fireEvent.click(screen.getByRole("button", { name: "选择暗色" }));
    fireEvent.click(screen.getByRole("button", { name: "选择暗色" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    view.unmount();
    delete document.documentElement.dataset.theme;
    renderTheme();
    expect(screen.getByLabelText("当前主题").textContent).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("跟随存储事件和同页事件，忽略无效主题", () => {
    renderTheme();
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "dark" })));
    expect(screen.getByLabelText("当前主题").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("theme-transition")).toBe(false);
    act(() => window.dispatchEvent(new CustomEvent("app:themechange", { detail: "light" })));
    expect(screen.getByLabelText("当前主题").textContent).toBe("light");
    act(() => window.dispatchEvent(new CustomEvent("app:themechange", { detail: "invalid" })));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
