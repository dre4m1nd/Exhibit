/**
 * The visual language of Exhibit: an amber-phosphor terminal on warm charcoal.
 *
 * Every value here is a contrast-checked token — the APCA gate (Lc 75 body /
 * 30 non-text on `ink`) has to pass before a colour ships, so no component
 * introduces an off-system hex. `danger` is the mark/border red; `dangerText`
 * is the lighter red that stays legible as small text on `ink`.
 */

export const theme = {
  accent: "#FFC21A",
  ink: "#0D0B08",
  text: "#F4EDE3",
  muted: "#D9CFBF",
  danger: "#FF6B4A",
  dangerText: "#FFC2B3",
  warn: "#FFC21A",
  ok: "#A6E8B0",
  info: "#9BDDEE",
  border: "#8A7A6A",
} as const;

export const SYMBOLS = {
  bullet: "•",
  tool: "▸",
  ok: "✓",
  fail: "✕",
  report: "❯",
} as const;
