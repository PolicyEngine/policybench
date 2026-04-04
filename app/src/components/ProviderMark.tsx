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

  return (
    <span
      className={`inline-flex items-center justify-center ${className}`}
      aria-label={label}
      title={label}
    >
      {provider === "anthropic" && (
        <Anthropic
          size={size}
          style={{ color: "#191919" }}
          aria-hidden="true"
        />
      )}
      {provider === "google" && <Google.Color size={size} aria-hidden="true" />}
      {provider === "openai" && (
        <OpenAI
          size={size}
          style={{ color: "#000000" }}
          aria-hidden="true"
        />
      )}
      {provider === "xai" && (
        <XAI
          size={size}
          style={{ color: "#000000" }}
          aria-hidden="true"
        />
      )}
    </span>
  );
}
