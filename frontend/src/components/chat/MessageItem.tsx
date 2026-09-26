import type { ChatMessage } from "@/api/types";
import { cn } from "@/lib/utils";
import { DiffSummary } from "./DiffSummary";

export function MessageItem({
  message,
  onFocusTask,
}: {
  message: ChatMessage;
  onFocusTask: (id: number) => void;
}) {
  if (message.role === "system") {
    return <div className="my-2 text-center text-xs text-muted-foreground">{message.content}</div>;
  }

  const isUser = message.role === "user";
  return (
    <div className={cn("my-1.5 flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
        )}
      >
        {message.content}
        {message.meta?.changes && message.meta.changes.length > 0 && (
          <DiffSummary
            summary={message.meta.summary ?? `Изменено задач: ${message.meta.changes.length}`}
            changes={message.meta.changes}
            onFocusTask={onFocusTask}
          />
        )}
      </div>
    </div>
  );
}
