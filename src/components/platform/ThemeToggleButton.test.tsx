import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { THEME_STORAGE_KEY } from "../../theme/theme";
import { ThemeToggleButton } from "./ThemeToggleButton";

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggleButton />
    </ThemeProvider>,
  );
}

/** 读取按钮当前的可访问名称。 */
function label() {
  return screen.getByRole("button").getAttribute("aria-label");
}

describe("ThemeToggleButton", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.dataset.theme = "light";
    document.documentElement.classList.remove("theme-transition");
  });

  afterEach(() => {
    cleanup();
    document.documentElement.dataset.theme = "light";
    document.documentElement.classList.remove("theme-transition");
  });

  it("首次访问为亮色，按钮展示月亮并说明将切到暗色", () => {
    renderToggle();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(label()).toBe("切换到暗色模式");
    expect(screen.getByRole("button").getAttribute("data-theme-mode")).toBe("light");
  });

  it("点击后切到暗色：图标变太阳、可访问名称更新、写入持久化", () => {
    renderToggle();
    fireEvent.click(screen.getByRole("button"));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(label()).toBe("切换到亮色模式");
    expect(screen.getByRole("button").getAttribute("data-theme-mode")).toBe("dark");
  });

  it("再点一次回到亮色", () => {
    renderToggle();
    const button = screen.getByRole("button");
    fireEvent.click(button);
    fireEvent.click(button);

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(label()).toBe("切换到暗色模式");
  });

  it("已保存暗色时首帧即为暗色并展示太阳", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    document.documentElement.dataset.theme = "dark";
    renderToggle();

    expect(label()).toBe("切换到亮色模式");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("存储值无效时首帧回退亮色", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "not-a-theme");
    document.documentElement.dataset.theme = "light";
    renderToggle();

    expect(label()).toBe("切换到暗色模式");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("同源其他标签页切换后本页跟随", () => {
    renderToggle();
    expect(label()).toBe("切换到暗色模式");

    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    fireEvent(
      window,
      new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "dark" }),
    );

    expect(label()).toBe("切换到亮色模式");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("按钮是原生 button，可被键盘聚焦与激活", () => {
    renderToggle();
    const button = screen.getByRole("button");
    expect(button.tagName).toBe("BUTTON");
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.keyDown(button, { key: "Enter" });
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
