// SVAR's own `ru` translation (@svar-ui/core-locales) mixes Latin look-alike letters into a
// few Cyrillic month names (e.g. "Maй" is Latin M+a, not Cyrillic М+а; "Oктябрь" is Latin O).
// That breaks search/selection and looks wrong when rendered. We take the upstream `ru` words
// wholesale (correct almost everywhere) and only patch the corrupted month arrays.
import { createElement, type FC, type ReactNode } from "react";
import { Locale } from "@svar-ui/react-core";
// @ts-expect-error -- @svar-ui/core-locales ships JS without its own type declarations.
import ruWords from "@svar-ui/core-locales/locales/ru";

const monthFull = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
];
const monthShort = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];

const words = {
  ...ruWords,
  calendar: { ...ruWords.calendar, monthFull, monthShort },
};

export function RuLocale({ children }: { children?: ReactNode }) {
  return createElement(Locale as FC<{ words?: unknown; children?: ReactNode }>, { words }, children);
}
