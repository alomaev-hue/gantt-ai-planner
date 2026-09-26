import { useEffect } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { SplitLayout } from "./SplitLayout";

// Records mounts/unmounts: ChatPanel aborts its in-flight chat request when it unmounts, so a pane
// that remounts on a tab switch (or when the window crosses the mobile breakpoint) would silently
// cancel a running agent turn.
function Probe({ name, log }: { name: string; log: string[] }) {
  useEffect(() => {
    log.push(`mount ${name}`);
    return () => {
      log.push(`unmount ${name}`);
    };
  }, [name, log]);
  return <div>{name} content</div>;
}

function setWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
}

afterEach(() => setWidth(1024));

test("on a phone, switching tabs hides the inactive pane instead of unmounting it", () => {
  setWidth(390);
  const log: string[] = [];
  render(<SplitLayout left={<Probe name="chart" log={log} />} right={<Probe name="chat" log={log} />} />);
  expect(screen.getByText("chart content")).toBeVisible();
  expect(screen.getByText("chat content")).not.toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Чат" }));
  expect(screen.getByText("chat content")).toBeVisible();
  expect(screen.getByText("chart content")).not.toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Диаграмма" }));
  expect(screen.getByText("chart content")).toBeVisible();
  expect(log).toEqual(["mount chart", "mount chat"]);
});

test("crossing the mobile breakpoint keeps both panes mounted", () => {
  setWidth(1024);
  const log: string[] = [];
  render(<SplitLayout left={<Probe name="chart" log={log} />} right={<Probe name="chat" log={log} />} />);
  expect(screen.getByText("chat content")).toBeVisible();

  act(() => {
    setWidth(390);
    window.dispatchEvent(new Event("resize"));
  });
  expect(screen.getByRole("button", { name: "Чат" })).toBeInTheDocument();
  act(() => {
    setWidth(1024);
    window.dispatchEvent(new Event("resize"));
  });
  expect(screen.getByText("chat content")).toBeVisible();
  expect(log).toEqual(["mount chart", "mount chat"]);
});
