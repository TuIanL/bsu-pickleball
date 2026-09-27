import { useEffect, useRef, useState } from "react";
import type { AutoRallyCue } from "../../hooks/useAutoRallyPlayback";

export const AUTO_RALLY_CUE_VISIBLE_MS = 2000;
export const AUTO_RALLY_CUE_MIN_GAP_MS = 1000;

export function RallyCueOverlay({ cue }: { cue: AutoRallyCue | null }) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<number | null>(null);
  const windowOpenRef = useRef(false);
  const windowEndRef = useRef<number | null>(null);
  const announcedCueIdRef = useRef<string | number | null>(null);

  useEffect(() => {
    if (!cue) {
      const wasWindowOpen = windowOpenRef.current;
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      windowOpenRef.current = false;
      // Leaving a rally after its cue already faded must not restart the quiet-gap
      // clock; auto-advance crosses this brief no-rally state while seeking.
      if (wasWindowOpen) windowEndRef.current = Date.now();
      announcedCueIdRef.current = null;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clears transient overlay state when playback leaves a rally.
      setVisible(false);
      return;
    }
    const cueKey = cue.cueKey ?? cue.id;
    if (announcedCueIdRef.current === cueKey) return;
    announcedCueIdRef.current = cueKey;

    if (windowOpenRef.current) {
      return;
    }
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (cue.cause === "autoAdvance" && windowEndRef.current !== null) {
      if (Date.now() - windowEndRef.current < AUTO_RALLY_CUE_MIN_GAP_MS) return;
    }

    windowOpenRef.current = true;
    setVisible(true);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      windowOpenRef.current = false;
      windowEndRef.current = Date.now();
      setVisible(false);
    }, AUTO_RALLY_CUE_VISIBLE_MS);
  }, [cue]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  if (!cue) return null;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden"
      data-auto-rally-cue={visible ? "visible" : "hidden"}
    >
      <span className={`auto-rally-cue${visible ? " auto-rally-cue--visible" : ""}`}>
        第{cue.ordinal}回合
      </span>
    </div>
  );
}
