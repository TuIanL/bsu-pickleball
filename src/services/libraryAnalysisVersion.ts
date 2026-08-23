import type { LibraryAnalysisJobView, LibraryItemRef, LibraryItemViewModel } from "./libraryAdapter";
import type { LibraryView } from "../components/library/viewCapabilities";
import type { NavigatePath } from "../app/navigationTypes";

export interface SelectedAnalysisResolution {
  requestedJobId?: string;
  selectedJob?: LibraryAnalysisJobView;
  selectedJobId?: string;
  explicit: boolean;
  invalidRequestedJob: boolean;
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "canceled"]);

/** Resolve a URL-owned selection strictly inside the current Library item. */
export function resolveSelectedAnalysisJob(
  item: LibraryItemViewModel,
  requestedJobId?: string | null,
): SelectedAnalysisResolution {
  const requested = requestedJobId?.trim() || undefined;
  const primaryId = item.primaryResultAnalysisJobId ?? item.primaryAnalysisJobId;
  const primary = primaryId ? item.analysisJobs.find((job) => job.id === primaryId) : undefined;
  if (!requested) {
    return {
      selectedJob: primary,
      selectedJobId: primary?.id ?? primaryId,
      explicit: false,
      invalidRequestedJob: false,
    };
  }

  const ownedPublicTerminal = item.analysisJobs.find(
    (job) => job.id === requested && TERMINAL_STATUSES.has(job.status),
  );
  if (ownedPublicTerminal) {
    return {
      requestedJobId: requested,
      selectedJob: ownedPublicTerminal,
      selectedJobId: ownedPublicTerminal.id,
      explicit: true,
      invalidRequestedJob: false,
    };
  }
  return {
    requestedJobId: requested,
    selectedJob: primary,
    selectedJobId: primary?.id ?? primaryId,
    explicit: false,
    invalidRequestedJob: true,
  };
}

export function analysisJobFromSearch(search: string): string | undefined {
  return new URLSearchParams(search).get("analysisJob")?.trim() || undefined;
}

export function buildLibraryWorkspacePath(
  ref: LibraryItemRef,
  options: {
    view?: LibraryView;
    analysisJobId?: string | null;
    search?: string;
    time?: string | number | null;
  } = {},
): NavigatePath {
  const params = new URLSearchParams(options.search ?? "");
  if (options.view) params.set("view", options.view);
  if (options.analysisJobId === null) params.delete("analysisJob");
  else if (options.analysisJobId) params.set("analysisJob", options.analysisJobId);
  if (options.time === null) params.delete("t");
  else if (options.time !== undefined) params.set("t", String(options.time));
  const query = params.toString();
  return `/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}${query ? `?${query}` : ""}` as NavigatePath;
}
