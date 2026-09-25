import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const MOBILE_BREAKPOINT = 768;
const LEFT_MIN_WIDTH = 360;
const RIGHT_MIN_WIDTH = 320;
const DEFAULT_LEFT_RATIO = 0.7;

export function SplitLayout({ left, right }: { left: ReactNode; right: ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < MOBILE_BREAKPOINT);
  const [tab, setTab] = useState<"chart" | "chat">("chart");
  const [leftWidth, setLeftWidth] = useState<number | null>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const clamp = useCallback((width: number, total: number) => {
    const max = Math.max(LEFT_MIN_WIDTH, total - RIGHT_MIN_WIDTH);
    return Math.min(Math.max(width, LEFT_MIN_WIDTH), max);
  }, []);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setLeftWidth(clamp(e.clientX - rect.left, rect.width));
    },
    [clamp],
  );

  const stopDragging = useCallback(() => {
    dragging.current = false;
    window.removeEventListener("pointermove", onPointerMove);
  }, [onPointerMove]);

  const startDragging = useCallback(() => {
    dragging.current = true;
    window.addEventListener("pointermove", onPointerMove);
    // `once` fires and detaches automatically, so `stopDragging` never needs to remove it itself.
    window.addEventListener("pointerup", stopDragging, { once: true });
  }, [onPointerMove, stopDragging]);

  useEffect(() => () => stopDragging(), [stopDragging]);

  if (isMobile) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex border-b border-border">
          <button
            type="button"
            className={cn(
              "flex-1 px-3 py-2 text-sm font-medium",
              tab === "chart" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground",
            )}
            onClick={() => setTab("chart")}
          >
            Диаграмма
          </button>
          <button
            type="button"
            className={cn(
              "flex-1 px-3 py-2 text-sm font-medium",
              tab === "chat" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground",
            )}
            onClick={() => setTab("chat")}
          >
            Чат
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">{tab === "chart" ? left : right}</div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex h-full min-h-0">
      <div
        className="min-h-0 overflow-auto"
        style={{ width: leftWidth ?? `${DEFAULT_LEFT_RATIO * 100}%`, flexShrink: 0 }}
      >
        {left}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        className="w-1 shrink-0 cursor-col-resize bg-border hover:bg-ring"
        onPointerDown={startDragging}
      />
      <div className="min-h-0 flex-1 overflow-auto">{right}</div>
    </div>
  );
}
