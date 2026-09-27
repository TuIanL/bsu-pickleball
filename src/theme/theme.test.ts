import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyTheme,
  DEFAULT_THEME,
  isThemeMode,
  persistTheme,
  readStoredTheme,
  resolveInitialTheme,
  THEME_STORAGE_KEY,
} from "./theme";

describe("theme：取值校验", () => {
  it("只接受 light 与 dark", () => {
    expect(isThemeMode("light")).toBe(true);
    expect(isThemeMode("dark")).toBe(true);
    expect(isThemeMode("DARK")).toBe(false);
    expect(isThemeMode("system")).toBe(false);
    expect(isThemeMode(null)).toBe(false);
    expect(isThemeMode(undefined)).toBe(false);
  });
});

describe("theme：存储读写容错", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("无存储时回退到默认亮色", () => {
    document.documentElement.dataset.theme = "";
    expect(resolveInitialTheme()).toBe(DEFAULT_THEME);
  });

  it("无效存储值回退到亮色，不跟随系统偏好", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "system");
    document.documentElement.dataset.theme = "";
    expect(readStoredTheme()).toBeNull();
    expect(resolveInitialTheme()).toBe("light");
  });

  it("有效存储值被保留", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    document.documentElement.dataset.theme = "";
    expect(readStoredTheme()).toBe("dark");
    expect(resolveInitialTheme()).toBe("dark");
  });

  it("存储不可用时仍能解析出亮色", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    document.documentElement.dataset.theme = "";
    expect(resolveInitialTheme()).toBe("light");
    expect(readStoredTheme()).toBeNull();
    spy.mockRestore();
  });

  it("写入失败不抛出（隐私模式/配额）", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => persistTheme("dark")).not.toThrow();
    spy.mockRestore();
  });

  it("写入后可读回", () => {
    persistTheme("dark");
    expect(readStoredTheme()).toBe("dark");
  });
});

describe("theme：DOM 落地", () => {
  afterEach(() => {
    document.documentElement.classList.remove("theme-transition");
    document.documentElement.dataset.theme = "light";
    vi.restoreAllMocks();
  });

  it("切换后写入 data-theme", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("用户主动切换才加过渡类，初始化不加", () => {
    applyTheme("dark", { animate: true });
    expect(document.documentElement.classList.contains("theme-transition")).toBe(true);

    document.documentElement.classList.remove("theme-transition");
    applyTheme("light");
    expect(document.documentElement.classList.contains("theme-transition")).toBe(false);
  });

  it("页面节点过多时跳过过渡，避免整页重绘", () => {
    // 造一个超过过渡预算的 DOM，模拟组件很多的重页面
    const host = document.createElement("div");
    for (let i = 0; i < 2600; i += 1) host.appendChild(document.createElement("span"));
    document.body.appendChild(host);

    try {
      applyTheme("dark", { animate: true });
      expect(document.documentElement.dataset.theme).toBe("dark");
      // 主题照样切换，只是不再挂过渡类
      expect(document.documentElement.classList.contains("theme-transition")).toBe(false);
    } finally {
      host.remove();
    }
  });

  it("系统开启减少动效时不加过渡类", () => {
    // jsdom 未实现 matchMedia，直接挂载返回 matches=true 的桩
    const original = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: () =>
        ({
          matches: true,
          media: "(prefers-reduced-motion: reduce)",
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        }) as MediaQueryList,
    });

    try {
      applyTheme("dark", { animate: true });
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.classList.contains("theme-transition")).toBe(false);
    } finally {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: original,
      });
    }
  });
});
