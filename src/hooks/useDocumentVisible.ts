import { useEffect, useState } from "react";

/** Tracks page visibility and updates only when the document becomes visible/hidden. */
export function useDocumentVisible(): boolean {
  const [isVisible, setIsVisible] = useState(() =>
    typeof document === "undefined" ? true : !document.hidden,
  );

  useEffect(() => {
    const updateVisibility = () => setIsVisible(!document.hidden);
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  return isVisible;
}
