import { chartColors } from "@policyengine/design-system/charts";
import { colors } from "@policyengine/design-system/tokens";

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
};

export type ProviderKey = "anthropic" | "google" | "openai" | "xai";

export const PROVIDER_LABELS: Record<ProviderKey, string> = {
  anthropic: "Anthropic",
  google: "Google",
  openai: "OpenAI",
  xai: "xAI",
};

export function getProviderForModel(model: string): ProviderKey | null {
  if (model.startsWith("claude-")) return "anthropic";
  if (model.startsWith("gemini-")) return "google";
  if (model.startsWith("gpt-")) return "openai";
  if (model.startsWith("grok-")) return "xai";
  return null;
}

export const MODEL_COLORS: Record<string, string> = {
  "claude-opus": chartColors.primary,
  "claude-opus-4.7": chartColors.primary,
  "claude-opus-4.6": chartColors.primary,
  "claude-haiku-4.5": colors.primary[300],
  "claude-sonnet-4.6": colors.primary[400],
  "grok-4.3": colors.gray[900],
  "grok-4.20": colors.gray[800],
  "grok-4.1-fast": colors.gray[700],
  "gpt-5.5": colors.secondary[700],
  "gpt-5.4": colors.secondary[700],
  "gpt-5.4-mini": colors.secondary[500],
  "gpt-5.4-nano": colors.secondary[300],
  "gemini-3.1-pro-preview": colors.warning,
  "gemini-3-flash-preview": colors.warning,
  "gemini-3.1-flash-lite-preview": colors.warning,
};

function mixWithSurface(color: string, amount: number): string {
  return `color-mix(in srgb, ${color} ${amount}%, ${colors.background.primary})`;
}

export const UI_COLORS = {
  border: colors.border.medium,
  borderLight: colors.border.light,
  chartLabel: colors.text.secondary,
  chartReference: colors.border.medium,
  inactive: colors.gray[400],
  primary: colors.primary[500],
  success: colors.primary[600],
  info: colors.info,
  warning: colors.warning,
  danger: colors.error,
} as const;

export function getPerformanceTextColor(score: number): string {
  if (score >= 90) return colors.primary[700];
  if (score >= 80) return colors.primary[600];
  if (score >= 70) return colors.info;
  if (score >= 60) return colors.warning;
  if (score >= 50) return colors.secondary[700];
  return colors.error;
}

export function getPerformanceSurfaceColor(score: number): string {
  if (score >= 90) return mixWithSurface(colors.primary[500], 18);
  if (score >= 80) return mixWithSurface(colors.primary[400], 14);
  if (score >= 70) return mixWithSurface(colors.info, 14);
  if (score >= 60) return mixWithSurface(colors.warning, 14);
  if (score >= 50) return mixWithSurface(colors.secondary[400], 14);
  return mixWithSurface(colors.error, 14);
}

export function getPredictionTextColor(error: number, truth: number): string {
  if (truth === 0 && error === 0) return colors.primary[700];
  const pctErr = truth !== 0 ? Math.abs(error / truth) : error !== 0 ? 1 : 0;
  if (pctErr <= 0.1) return colors.primary[700];
  if (pctErr <= 0.25) return colors.info;
  if (pctErr <= 0.5) return colors.warning;
  return colors.error;
}
