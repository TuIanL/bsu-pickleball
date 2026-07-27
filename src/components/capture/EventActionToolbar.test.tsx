import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { QuickEventDef } from "../../services/timelineQuickEvents";
import { EventActionToolbar } from "./EventActionToolbar";

const events: QuickEventDef[] = [
  { type: "rally_result_a", label: "A 方胜", source: "manual", note: "", payload: {}, group: "match" },
  { type: "rally_result_b", label: "B 方胜", source: "manual", note: "", payload: {}, group: "match" },
  { type: "rally_replay", label: "重打", source: "manual", note: "", payload: {}, group: "match" },
  { type: "undo", label: "撤销", source: "manual", note: "", payload: {}, group: "auxiliary" },
];

describe("EventActionToolbar", () => {
  it("renders explicit result actions in the primary group", () => {
    render(<EventActionToolbar events={events} onAction={() => {}} />);
    expect(screen.getByText("主要操作")).toBeTruthy();
    expect(screen.getByRole("button", { name: "A 方胜" }).className).toContain("flex-1");
    expect(screen.getByRole("button", { name: "B 方胜" }).className).toContain("flex-1");
    expect(screen.queryByRole("button", { name: "分结束" })).toBeNull();
  });

  it("disables every action while a command is pending", () => {
    const onAction = vi.fn();
    const { container } = render(<EventActionToolbar events={events} disabled onAction={onAction} />);
    const button = container.querySelector('button[aria-label="A 方胜"]') as HTMLButtonElement;
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(onAction).not.toHaveBeenCalled();
  });
});
