import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// 导入主应用组件
import App from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";
// 导入全局样式
import "./index.css";

// 创建 React 根节点并渲染应用
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>
);
