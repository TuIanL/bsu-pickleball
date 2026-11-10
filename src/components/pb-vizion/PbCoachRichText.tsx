// =============================================================
// 教学助教回答的轻量排版
// -------------------------------------------------------------
// 模型天然会用 **加粗** 和「1. / -」列表；报告页不引入 md 渲染库，
// 这里只处理这三种最常见语法，避免把 ** 原样显示给教师。
// =============================================================
import { Fragment, type ReactNode } from "react";

const LIST_PREFIX = /^\s*(?:\d+[.、)]|[-*·])\s+/;

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={index} className="font-bold text-[var(--pb-text-primary)]">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function Cursor() {
  return <span className="pb-coach-cursor">▍</span>;
}

export default function PbCoachRichText({
  text,
  streaming,
}: {
  text: string;
  streaming?: boolean;
}) {
  const blocks = text.split(/\n{2,}/).filter((block) => block.trim().length > 0);

  return (
    <div className="space-y-1.5 text-[13px] leading-[1.7] text-[var(--pb-text-primary)]">
      {blocks.map((block, blockIndex) => {
        const isLast = blockIndex === blocks.length - 1;
        const lines = block
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => LIST_PREFIX.test(line));

        if (isList) {
          return (
            <ul className="space-y-1" key={blockIndex}>
              {lines.map((line, lineIndex) => (
                <li className="flex gap-1.5" key={lineIndex}>
                  <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--pb-primary)]" />
                  <span>
                    {renderInline(line.replace(LIST_PREFIX, ""))}
                    {isLast && lineIndex === lines.length - 1 && streaming ? <Cursor /> : null}
                  </span>
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p className="whitespace-pre-wrap" key={blockIndex}>
            {renderInline(block)}
            {isLast && streaming ? <Cursor /> : null}
          </p>
        );
      })}
      {blocks.length === 0 && streaming ? <Cursor /> : null}
    </div>
  );
}
