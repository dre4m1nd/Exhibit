/**
 * Terminal cell arithmetic.
 *
 * Every width in the TUI is measured in terminal cells, never in code points:
 * a CJK glyph advances two columns, so padding by `string.length` leaves frames
 * ragged and columns misaligned.
 */

/** Width of one code point in terminal cells (CJK and emoji count as two). */
export function charWidth(char: string): number {
  const code = char.codePointAt(0) ?? 0;
  if (
    code === 0 ||
    code < 32 ||
    (code >= 0x0300 && code <= 0x036f) ||
    (code >= 0xfe00 && code <= 0xfe0f)
  ) {
    return 0;
  }
  if (
    (code >= 0x1100 && code <= 0x115f) ||
    code === 0x2329 ||
    code === 0x232a ||
    (code >= 0x2e80 && code <= 0xa4cf) ||
    (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe30 && code <= 0xfe6f) ||
    (code >= 0xff00 && code <= 0xff60) ||
    (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) ||
    (code >= 0x20000 && code <= 0x3fffd)
  ) {
    return 2;
  }
  return 1;
}

export function displayWidth(text: string): number {
  let width = 0;
  for (const char of text) width += charWidth(char);
  return width;
}

/** Clip to `width` cells, keeping the head; appends `…` when text is cut. */
export function truncate(text: string, width: number, marker = "…"): string {
  if (displayWidth(text) <= width) return text;
  const budget = Math.max(0, width - charWidth(marker));
  let out = "";
  let used = 0;
  for (const char of text) {
    const cells = charWidth(char);
    if (used + cells > budget) break;
    out += char;
    used += cells;
  }
  return out + marker;
}

/** Clip to `width` cells keeping the tail, so a caret stays visible. */
export function truncateLeft(text: string, width: number, marker = "…"): string {
  if (displayWidth(text) <= width) return text;
  const budget = Math.max(0, width - charWidth(marker));
  const chars = [...text];
  let out = "";
  let used = 0;
  for (let index = chars.length - 1; index >= 0; index -= 1) {
    const char = chars[index] ?? "";
    const cells = charWidth(char);
    if (used + cells > budget) break;
    out = char + out;
    used += cells;
  }
  return marker + out;
}

/** Pad or clip to exactly `width` cells (clip keeps a trailing `…`). */
export function padTo(text: string, width: number): string {
  const clipped = truncate(text, width);
  return clipped + " ".repeat(Math.max(0, width - displayWidth(clipped)));
}
