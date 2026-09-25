import { parseSSE } from "./chatStream";

test("parses complete events and keeps the rest", () => {
  const { events, rest } = parseSSE('event: text_delta\ndata: {"type":"text_delta","text":"Привет"}\n\n: ping\n\nevent: done\ndata: {"ty');
  expect(events).toEqual([{ event: "text_delta", data: '{"type":"text_delta","text":"Привет"}' }]);
  expect(rest).toBe('event: done\ndata: {"ty');
});

test("handles CRLF and multi-line data", () => {
  const { events } = parseSSE("event: x\r\ndata: a\r\ndata: b\r\n\r\n");
  expect(events).toEqual([{ event: "x", data: "a\nb" }]);
});
