/** POST /v1/visibility/live response (api/visibility_live_api.py). Observed answers only. */
export interface LiveModel {
  asked: number; questions: number; mentioned: number; cited: number; top3: number; mention_rate: number | null;
  best_position: number | null; partial: boolean; brands_named_instead: { brand: string; count: number }[];
}
export interface LiveVisibility {
  available: boolean; reason?: string; models?: Record<string, LiveModel>; cost_usd?: number;
  questions_used?: { id: string; text: string }[]; caveats?: string[];
}

const NAMES: Record<string, string> = { "openai:gpt-4o-mini": "ChatGPT (GPT-4o mini)", "anthropic:claude-haiku-4-5-20251001": "Claude (Haiku 4.5)" };
export const liveModelName = (id: string) => NAMES[id] ?? id;
