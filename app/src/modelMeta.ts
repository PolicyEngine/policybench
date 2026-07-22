// Color references go through @policyengine/ui-kit CSS variables (defined in
// `app/src/app/globals.css` via the imported theme). Browsers resolve `var(...)`
// strings inside both inline `style` attributes and chart props, so we
// can keep the runtime values out of the JS bundle.

export const MODEL_ORDER = [
  "claude-fable-5",
  "claude-opus-4.8",
  "claude-opus-4.7",
  "claude-sonnet-5",
  "claude-sonnet-4.6",
  "claude-haiku-4.5",
  "grok-4.3",
  "grok-4.5",
  "grok-build-0.1",
  "gpt-5.6-sol",
  "gpt-5.6-terra",
  "gpt-5.6-luna",
  "gpt-5.5",
  "gpt-5.4-mini",
  "gpt-5.4-nano",
  "gemini-3.1-pro-preview",
  "gemini-3.6-flash",
  "gemini-3.5-flash",
  "gemini-3-flash-preview",
  "gemini-3.1-flash-lite-preview",
  "deepseek-v4-pro",
  "deepseek-v4-flash",
  "kimi-k3",
  "kimi-k2.6",
  "glm-5.2",
  "minimax-m3",
  "qwen-3.7-max",
] as const;

export const MODEL_LABELS: Record<string, string> = {
  "claude-fable-5": "Claude Fable 5",
  "claude-opus-4.8": "Claude Opus 4.8",
  "claude-opus-4.7": "Claude Opus 4.7",
  "claude-haiku-4.5": "Claude Haiku 4.5",
  "claude-sonnet-5": "Claude Sonnet 5",
  "claude-sonnet-4.6": "Claude Sonnet 4.6",
  "grok-4.3": "Grok 4.3",
  "grok-4.5": "Grok 4.5",
  "grok-build-0.1": "Grok Build 0.1",
  "gpt-5.6-sol": "GPT-5.6 Sol",
  "gpt-5.6-terra": "GPT-5.6 Terra",
  "gpt-5.6-luna": "GPT-5.6 Luna",
  "gpt-5.5": "GPT-5.5",
  "gpt-5.4-mini": "GPT-5.4 mini",
  "gpt-5.4-nano": "GPT-5.4 nano",
  "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
  "gemini-3.6-flash": "Gemini 3.6 Flash",
  "gemini-3.5-flash": "Gemini 3.5 Flash",
  "gemini-3-flash-preview": "Gemini 3 Flash Preview",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite Preview",
  "deepseek-v4-pro": "DeepSeek V4 Pro",
  "deepseek-v4-flash": "DeepSeek V4 Flash",
  "kimi-k3": "Kimi K3",
  "kimi-k2.6": "Kimi K2.6",
  "glm-5.2": "GLM-5.2",
  "minimax-m3": "MiniMax M3",
  "qwen-3.7-max": "Qwen 3.7 Max",
};

export type ProviderKey =
  | "alibaba"
  | "anthropic"
  | "deepseek"
  | "google"
  | "minimax"
  | "moonshot"
  | "openai"
  | "xai"
  | "zai";

// First public availability (paid tiers count; trusted-tester previews do
// not). Mirrors policybench/paper_results.py MODEL_RELEASE_DATES, where each
// date carries its source; update both together.
export const MODEL_RELEASE_DATES: Record<string, string> = {
  "claude-fable-5": "2026-06-09",
  "claude-sonnet-5": "2026-06-30",
  "claude-opus-4.8": "2026-05-28",
  "claude-opus-4.7": "2026-04-16",
  "claude-haiku-4.5": "2025-10-15",
  "claude-sonnet-4.6": "2026-02-17",
  "gemini-3-flash-preview": "2025-12-17",
  "gemini-3.1-pro-preview": "2026-02-19",
  "gemini-3.5-flash": "2026-05-19",
  "gemini-3.6-flash": "2026-07-21",
  "gemini-3.1-flash-lite-preview": "2026-03-03",
  "gpt-5.4-mini": "2026-03-17",
  "gpt-5.4-nano": "2026-03-17",
  "gpt-5.5": "2026-04-23",
  "gpt-5.6-sol": "2026-07-09",
  "gpt-5.6-terra": "2026-07-09",
  "gpt-5.6-luna": "2026-07-09",
  "grok-4.3": "2026-04-17",
  "grok-4.5": "2026-07-08",
  "grok-build-0.1": "2026-05-29",
  "deepseek-v4-pro": "2026-04-24",
  "deepseek-v4-flash": "2026-04-24",
  "kimi-k2.6": "2026-04-20",
  "kimi-k3": "2026-07-16",
  "glm-5.2": "2026-06-13",
  "minimax-m3": "2026-06-01",
  "qwen-3.7-max": "2026-05-19",
};

export const PROVIDER_LABELS: Record<ProviderKey, string> = {
  alibaba: "Alibaba",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  google: "Google",
  minimax: "MiniMax",
  moonshot: "Moonshot AI",
  openai: "OpenAI",
  xai: "xAI",
  zai: "Z.ai",
};

export function getProviderForModel(model: string): ProviderKey | null {
  if (model.startsWith("claude-")) return "anthropic";
  if (model.startsWith("deepseek-")) return "deepseek";
  if (model.startsWith("gemini-")) return "google";
  if (model.startsWith("glm-")) return "zai";
  if (model.startsWith("gpt-")) return "openai";
  if (model.startsWith("grok-")) return "xai";
  if (model.startsWith("kimi-")) return "moonshot";
  if (model.startsWith("minimax-")) return "minimax";
  if (model.startsWith("qwen-")) return "alibaba";
  return null;
}

/**
 * Put curated models in display order without hiding models that the data
 * bundle gained before this metadata file was updated. Unknown IDs sort by
 * their stable machine names so their order does not depend on input traversal.
 */
export function orderModels(models: Iterable<string>): string[] {
  const uniqueModels = new Set(models);
  const knownModels = MODEL_ORDER.filter((model) => uniqueModels.delete(model));
  return [...knownModels, ...Array.from(uniqueModels).sort()];
}

// One frontier flagship per provider — used by the scenario explorer's
// "Frontier only" filter (default on) so the table stays scannable. A provider
// can list fallbacks after its current flagship so an older frozen data bundle
// still retains one visible model (for example GPT-5.5 before Sol is folded).
const FRONTIER_MODEL_GROUPS = [
  ["claude-fable-5", "claude-opus-4.8"],
  ["gpt-5.6-sol", "gpt-5.5"],
  ["grok-4.5", "grok-4.3"],
  ["gemini-3.1-pro-preview"],
  ["deepseek-v4-pro"],
  ["kimi-k3", "kimi-k2.6"],
  ["glm-5.2"],
  ["minimax-m3"],
  ["qwen-3.7-max"],
] as const;

export const FRONTIER_MODELS: readonly string[] = FRONTIER_MODEL_GROUPS.map(
  ([current]) => current,
);

export function frontierModelsFor(models: Iterable<string>): string[] {
  const available = new Set(models);
  const selected: string[] = [];
  const representedProviders = new Set<ProviderKey>();
  for (const candidates of FRONTIER_MODEL_GROUPS) {
    const model = candidates.find((candidate) => available.has(candidate));
    if (!model) continue;
    selected.push(model);
    const provider = getProviderForModel(model);
    if (provider) representedProviders.add(provider);
  }

  // A newly added provider or a frozen bundle without a named candidate still
  // gets one visible model instead of a provider chip that empties the table.
  for (const model of orderModels(available)) {
    const provider = getProviderForModel(model);
    if (!provider || representedProviders.has(provider)) continue;
    selected.push(model);
    representedProviders.add(provider);
  }
  return selected;
}

export function isFrontierModel(model: string): boolean {
  return FRONTIER_MODELS.includes(model);
}

const TEAL_400 = "var(--color-teal-400)";
const TEAL_500 = "var(--color-teal-500)";
const TEAL_600 = "var(--color-teal-600)";
const TEAL_700 = "var(--color-teal-700)";
const SECONDARY_400 = "var(--color-gray-400)";
const SECONDARY_700 = "var(--color-gray-700)";
const INFO = "var(--color-info)";
const WARNING = "var(--color-warning)";
const ERROR = "var(--color-error)";

function mixWithBackground(color: string, amount: number): string {
  return `color-mix(in srgb, ${color} ${amount}%, var(--background))`;
}

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
