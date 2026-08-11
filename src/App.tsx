// 导入 React 核心钩子
import { useCallback, useEffect, useState } from "react";
import type { NavigateOptions, NavigatePath, RouteState } from "./app/navigationTypes";
import { parseLocation } from "./app/router";
import { AppRouter } from "./app/AppRouter";
import { AppShell } from "./components/platform/AppShell";
import { getRecentAnalysisJob, RECENT_ANALYSIS_JOB_EVENT } from "./services/analysisClient";
import type { AnalysisJobSummary } from "./types/report";

function App() {
  // 初始化路由状态
  const [route, setRoute] = useState<RouteState>(() => parseLocation(window.location.pathname, window.location.search));
  const [recentJob, setRecentJob] = useState<AnalysisJobSummary | null>(() => getRecentAnalysisJob());

  // 自定义导航函数，支持平滑滚动到顶部
  const navigate = useCallback((path: NavigatePath, options: NavigateOptions = {}) => {
    const url = new URL(path, window.location.origin);
    const nextRoute = parseLocation(url.pathname, url.search);
    const nextHref = `${url.pathname}${url.search}${url.hash}`;
    if (options.replace) {
      window.history.replaceState({}, "", nextHref);
    } else {
      window.history.pushState({}, "", nextHref);
    }
    setRoute(nextRoute);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // 监听浏览器前进/后退事件
  useEffect(() => {
    const handlePopState = () => setRoute(parseLocation(window.location.pathname, window.location.search));
    window.addEventListener("popstate", handlePopState);

    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    const handleRecentJobChange = () => setRecentJob(getRecentAnalysisJob());
    window.addEventListener(RECENT_ANALYSIS_JOB_EVENT, handleRecentJobChange);
    window.addEventListener("storage", handleRecentJobChange);

    return () => {
      window.removeEventListener(RECENT_ANALYSIS_JOB_EVENT, handleRecentJobChange);
      window.removeEventListener("storage", handleRecentJobChange);
    };
  }, []);

  return (
    <AppShell shellMode={route.shellMode} navigationSection={route.navigationSection} onNavigate={navigate}>
      <AppRouter route={route} onNavigate={navigate} recentJob={recentJob} />
    </AppShell>
  );
}

export default App;
