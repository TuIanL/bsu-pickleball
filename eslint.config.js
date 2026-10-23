import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "backend/.venv", "backend/data", "node_modules", "**/.runtime/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        window: "readonly",
        document: "readonly",
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true }
      ],
      // 注意：不要为了让 CI 变绿而全局降级 react-hooks v6 的规则。
      // 存量不符合项在具体代码行上用 eslint-disable-next-line 显式豁免并写明
      // 原因与重构方向，这样新代码仍会被拦，存量也不会被几十条 warning 淹没。
      // （react-hooks/exhaustive-deps 在 recommended 里本就是 warn，那是既有基线；
      //  set-state-in-effect 是 error，保持 error。）
    },
  }
);
