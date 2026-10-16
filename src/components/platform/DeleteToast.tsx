import { useEffect } from "react";
import { X } from "lucide-react";

export type DeleteToastKind = "success" | "attention";

export interface DeleteToastData {
  kind: DeleteToastKind;
  message: string;
}

interface DeleteToastProps {
  toast: DeleteToastData;
  onClose: () => void;
}

/**
 * 右下角浮动的删除/取消操作结果 toast。
 *
 * - success：绿色单行，3 秒后自动消失（仅定时器，不显示倒计时/进度条）。
 * - attention：琥珀色，带 × 关闭按钮，需用户手动关闭。
 * 固定定位，不占页面内容区。
 */
export default function DeleteToast({ toast, onClose }: DeleteToastProps) {
  const { kind, message } = toast;

  useEffect(() => {
    // 仅 success 自动消失；attention 常驻等待手动关闭。
    if (kind !== "success") return;
    const timer = setTimeout(onClose, 3000);
    return () => clearTimeout(timer);
  }, [kind, message, onClose]);

  const attention = kind === "attention";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`toast-in fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-2 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg ${
        attention
          ? "border-[var(--ui-warning-border-strong)] bg-[var(--ui-warning-surface)] text-[var(--ui-warning-deeper)]"
          : "border-[var(--ui-success-border)] bg-[var(--ui-success-soft)] text-[var(--ui-success-ink)]"
      }`}
    >
      <p className="flex-1 font-medium leading-5">{message}</p>
      {attention && (
        <button
          type="button"
          aria-label="关闭提示"
          onClick={onClose}
          className="shrink-0 rounded p-0.5 text-[var(--ui-warning-deep)] transition hover:bg-[var(--ui-warning-soft-2)]"
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
