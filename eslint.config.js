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
      // eslint-plugin-react-hooks v6 起把 React Compiler 的规则纳入 recommended。
      // "props 变化时重置本地 state" 是本代码库的既有模式（如分析名册确认页），
      // 改写为渲染期派生会牵动业务语义，风险高于收益：先降级为 warn，逐步迁移。
      // 注意 refs 仍是 error —— 渲染期读写 ref 在并发渲染下是真实缺陷，应修代码。
      "react-hooks/set-state-in-effect": "warn",
    },
  }
);
