// Color references go through @policyengine/ui-kit CSS variables (defined in
// `app/src/app/globals.css` via the imported theme). Browsers resolve `var(...)`
// strings inside both inline `style` attributes and Recharts chart props, so we
// can keep the runtime values out of the JS bundle.

export const MODEL_ORDER = [
  "claude-opus-4.7",
  "claude-sonnet-4.6",
  "claude-haiku-4.5",
  "grok-4.3",
  "grok-4.20",
  "grok-4.1-fast",
  "gpt-5.5",
  "gpt-5.4-mini",
  "gpt-5.4-nano",
  "gemini-3.1-pro-preview",
  "gemini-3-flash-preview",
  "gemini-3.1-flash-lite-preview",
  "deepseek-v4-pro",
  "deepseek-v4-flash",
] as const;

export const MODEL_LABELS: Record<string, string> = {
  "claude-opus": "Claude Opus 4.7",
  "claude-opus-4.7": "Claude Opus 4.7",
  "claude-opus-4.6": "Claude Opus 4.6",
  "claude-haiku-4.5": "Claude Haiku 4.5",
  "claude-sonnet-4.6": "Claude Sonnet 4.6",
  "grok-4.3": "Grok 4.3",
  "grok-4.20": "Grok 4.20",
  "grok-4.1-fast": "Grok 4.1 Fast",
  "gpt-5.5": "GPT-5.5",
  "gpt-5.4": "GPT-5.4",
  "gpt-5.4-mini": "GPT-5.4 mini",
  "gpt-5.4-nano": "GPT-5.4 nano",
  "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
  "gemini-3-flash-preview": "Gemini 3 Flash Preview",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite Preview",
  "deepseek-v4-pro": "DeepSeek V4 Pro",
  "deepseek-v4-flash": "DeepSeek V4 Flash",
};

export type ProviderKey =
  | "anthropic"
  | "deepseek"
  | "google"
  | "openai"
  | "xai";

export const PROVIDER_LABELS: Record<ProviderKey, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  google: "Google",
  openai: "OpenAI",
  xai: "xAI",
};

export function getProviderForModel(model: string): ProviderKey | null {
  if (model.startsWith("claude-")) return "anthropic";
  if (model.startsWith("deepseek-")) return "deepseek";
  if (model.startsWith("gemini-")) return "google";
  if (model.startsWith("gpt-")) return "openai";
  if (model.startsWith("grok-")) return "xai";
  return null;
}

// One frontier flagship per provider — used by the leaderboard's
// "Frontier only" filter (default on) so the table stays scannable.
export const FRONTIER_MODELS: readonly string[] = [
  "claude-opus-4.7",
  "gpt-5.5",
  "grok-4.3",
  "gemini-3.1-pro-preview",
  "deepseek-v4-pro",
];

export function isFrontierModel(model: string): boolean {
  return FRONTIER_MODELS.includes(model);
}

const TEAL_500 = "var(--color-teal-500)";
const TEAL_300 = "var(--color-teal-300)";
const TEAL_400 = "var(--color-teal-400)";
const TEAL_600 = "var(--color-teal-600)";
const TEAL_700 = "var(--color-teal-700)";
const GRAY_400 = "var(--color-gray-400)";
const GRAY_700 = "var(--color-gray-700)";
const GRAY_800 = "var(--color-gray-800)";
const GRAY_900 = "var(--color-gray-900)";
const SECONDARY_300 = "var(--color-gray-300)";
const SECONDARY_400 = "var(--color-gray-400)";
const SECONDARY_500 = "var(--color-gray-500)";
const SECONDARY_700 = "var(--color-gray-700)";
const BLUE_400 = "var(--color-blue-400)";
const BLUE_700 = "var(--color-blue-700)";
const INFO = "var(--color-info)";
const WARNING = "var(--color-warning)";
const ERROR = "var(--color-error)";
const BORDER_LIGHT = "var(--border-light)";
const BORDER_MEDIUM = "var(--border-medium)";
const TEXT_SECONDARY = "var(--text-secondary)";

export const MODEL_COLORS: Record<string, string> = {
  "claude-opus": TEAL_500,
  "claude-opus-4.7": TEAL_500,
  "claude-opus-4.6": TEAL_500,
  "claude-haiku-4.5": TEAL_300,
  "claude-sonnet-4.6": TEAL_400,
  "grok-4.3": GRAY_900,
  "grok-4.20": GRAY_800,
  "grok-4.1-fast": GRAY_700,
  "gpt-5.5": SECONDARY_700,
  "gpt-5.4": SECONDARY_700,
  "gpt-5.4-mini": SECONDARY_500,
  "gpt-5.4-nano": SECONDARY_300,
  "gemini-3.1-pro-preview": WARNING,
  "gemini-3-flash-preview": WARNING,
  "gemini-3.1-flash-lite-preview": WARNING,
  "deepseek-v4-pro": BLUE_700,
  "deepseek-v4-flash": BLUE_400,
};

function mixWithBackground(color: string, amount: number): string {
  return `color-mix(in srgb, ${color} ${amount}%, var(--background))`;
}

export const UI_COLORS = {
  border: BORDER_MEDIUM,
  borderLight: BORDER_LIGHT,
  chartLabel: TEXT_SECONDARY,
  chartReference: BORDER_MEDIUM,
  inactive: GRAY_400,
  primary: TEAL_500,
  success: TEAL_600,
  info: INFO,
  warning: WARNING,
  danger: ERROR,
} as const;

export function getPerformanceTextColor(score: number): string {
  if (score >= 90) return TEAL_700;
  if (score >= 80) return TEAL_600;
  if (score >= 70) return INFO;
  if (score >= 60) return WARNING;
  if (score >= 50) return SECONDARY_700;
  return ERROR;
}

export function getPerformanceSurfaceColor(score: number): string {
  if (score >= 90) return mixWithBackground(TEAL_500, 18);
  if (score >= 80) return mixWithBackground(TEAL_400, 14);
  if (score >= 70) return mixWithBackground(INFO, 14);
  if (score >= 60) return mixWithBackground(WARNING, 14);
  if (score >= 50) return mixWithBackground(SECONDARY_400, 14);
  return mixWithBackground(ERROR, 14);
}

export function getPredictionTextColor(error: number, truth: number): string {
  if (truth === 0 && Math.abs(error) <= 1) return TEAL_700;
  const pctErr = truth !== 0 ? Math.abs(error / truth) : error !== 0 ? 1 : 0;
  if (pctErr <= 0.1) return TEAL_700;
  if (pctErr <= 0.25) return INFO;
  if (pctErr <= 0.5) return WARNING;
  return ERROR;
}
