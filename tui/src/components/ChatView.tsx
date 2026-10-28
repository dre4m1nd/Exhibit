import type { TraceStep } from "../trace.js";

/** One entry in the chat transcript. Rendering lives in ChatViewport. */
export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  text: string;
  kind?: "message" | "tool" | "tool-result" | "trace";
  ok?: boolean;
  duration?: number;
  steps?: TraceStep[];
  collapsedSummary?: string;
}
