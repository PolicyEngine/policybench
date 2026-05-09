import { Anthropic, Google, OpenAI, XAI } from "@lobehub/icons";
import { PROVIDER_LABELS, type ProviderKey } from "../modelMeta";

export default function ProviderMark({
  provider,
  size = 14,
  className = "",
}: {
  provider: ProviderKey | null;
  size?: number;
  className?: string;
}) {
  if (!provider) {
    return (
      <span
        aria-hidden="true"
        className={`block rounded-full bg-current ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  const label = PROVIDER_LABELS[provider];

  // role="img" + aria-label gives screen readers the provider name once.
  // Inner SVGs stay aria-hidden so they don't double-announce. Inheriting
  // currentColor keeps the icon legible if it's ever rendered on a dark
  // surface (e.g. an active pill).
  return (
    <span
      role="img"
      aria-label={label}
      className={`inline-flex items-center justify-center text-text ${className}`}
    >
      {provider === "anthropic" && <Anthropic size={size} color="currentColor" aria-hidden="true" />}
      {provider === "google" && <Google.Color size={size} aria-hidden="true" />}
      {provider === "openai" && <OpenAI size={size} color="currentColor" aria-hidden="true" />}
      {provider === "xai" && <XAI size={size} color="currentColor" aria-hidden="true" />}
    </span>
  );
}
