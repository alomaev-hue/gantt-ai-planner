import { render, screen } from "@testing-library/react";
import { MessageItem } from "./MessageItem";

test("**bold** from the model renders as bold, without literal asterisks", () => {
  render(
    <MessageItem
      message={{ id: 1, role: "assistant", content: "Окончание сдвинулось на **20.11.2026** (+3 дня).", meta: {}, created_at: "" }}
      onFocusTask={() => {}}
    />,
  );
  const strong = screen.getByText("20.11.2026");
  expect(strong.tagName).toBe("STRONG");
  expect(strong.parentElement?.textContent).toBe("Окончание сдвинулось на 20.11.2026 (+3 дня).");
});

test("user text is shown verbatim (asterisks the user typed stay)", () => {
  render(<MessageItem message={{ id: 2, role: "user", content: "2**3 **x**", meta: {}, created_at: "" }} onFocusTask={() => {}} />);
  expect(screen.getByText("2**3 **x**")).toBeInTheDocument();
});
