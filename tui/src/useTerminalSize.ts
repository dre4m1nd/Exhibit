/** Terminal geometry, kept in sync with resize events. */

import { useEffect, useState } from "react";

export interface TerminalSize {
  rows: number;
  columns: number;
}

export function terminalSize(): TerminalSize {
  return {
    rows: process.stdout.rows || 24,
    columns: process.stdout.columns || 80,
  };
}

/** Current terminal size; re-renders on resize. */
export function useTerminalSize(): TerminalSize {
  const [size, setSize] = useState(terminalSize);
  useEffect(() => {
    const onResize = () => setSize(terminalSize());
    process.stdout.on("resize", onResize);
    return () => {
      process.stdout.off("resize", onResize);
    };
  }, []);
  return size;
}
