export const MODEL_ORDER = [
  "claude-opus",
  "claude-sonnet-4.6",
  "gpt-5.4",
  "gemini-3.1-pro-preview",
  "gpt-5.2",
  "claude-sonnet-4.5",
  "gemini-3-pro",
] as const;

export const MODEL_LABELS: Record<string, string> = {
  "claude-opus": "Claude Opus 4.6",
  "claude-sonnet-4.5": "Claude Sonnet 4.5",
  "claude-sonnet-4.6": "Claude Sonnet 4.6",
  "gpt-5.2": "GPT-5.2",
  "gpt-5.4": "GPT-5.4",
  "gemini-3-pro": "Gemini 3 Pro",
  "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
};

export const MODEL_COLORS: Record<string, string> = {
  "claude-opus": "#00d4ff",
  "claude-sonnet-4.5": "#ffaa00",
  "claude-sonnet-4.6": "#00ff88",
  "gpt-5.2": "#ff4466",
  "gpt-5.4": "#ff4466",
  "gemini-3-pro": "#c4a04c",
  "gemini-3.1-pro-preview": "#c4a04c",
};
