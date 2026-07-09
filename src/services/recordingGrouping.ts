import type { FieldSession, RecordingSession } from "../types/report";

export interface RecordingGroup {
  fieldSession: FieldSession | null;
  recordings: RecordingSession[];
}

/**
 * 将录制按采集任务(FieldSession)分组，用于在「录制视频任务」Tab 中展示。
 *
 * - field_session_id 为空或指向不存在采集任务的录制归入未归类组(fieldSession = null)。
 * - 具名分组按"组内最近录制时间"倒序；空分组按 FieldSession.created_at 倒序。
 * - 未归类组始终排在分组列表最底部。
 * - 组内录制按 started_at 倒序。
 * - 所有具名采集任务(含 0 条录制的空分组)都会被保留，不遗漏。
 */
export function groupRecordingsByFieldSession(
  fieldSessions: FieldSession[],
  recordings: RecordingSession[],
): RecordingGroup[] {
  const fsById = new Map(fieldSessions.map((fs) => [fs.id, fs]));

  const namedMap = new Map<string, RecordingSession[]>();
  const uncategorized: RecordingSession[] = [];

  for (const recording of recordings) {
    const fsId = recording.field_session_id;
    if (fsId && fsById.has(fsId)) {
      const list = namedMap.get(fsId);
      if (list) {
        list.push(recording);
      } else {
        namedMap.set(fsId, [recording]);
      }
    } else {
      uncategorized.push(recording);
    }
  }

  const byStartedAtDesc = (a: RecordingSession, b: RecordingSession): number =>
    a.started_at < b.started_at ? 1 : a.started_at > b.started_at ? -1 : 0;

  const namedGroups: RecordingGroup[] = fieldSessions.map((fs) => ({
    fieldSession: fs,
    recordings: (namedMap.get(fs.id) ?? []).slice().sort(byStartedAtDesc),
  }));

  // 具名分组排序：有录制的按"组内最近录制时间"倒序；空分组按 created_at 倒序
  namedGroups.sort((a, b) => {
    const aTime = a.recordings.length > 0 ? a.recordings[0].started_at : a.fieldSession?.created_at ?? "";
    const bTime = b.recordings.length > 0 ? b.recordings[0].started_at : b.fieldSession?.created_at ?? "";
    return aTime < bTime ? 1 : aTime > bTime ? -1 : 0;
  });

  if (uncategorized.length > 0) {
    namedGroups.push({
      fieldSession: null,
      recordings: uncategorized.slice().sort(byStartedAtDesc),
    });
  }

  return namedGroups;
}
