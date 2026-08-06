import {
  Alibaba,
  Anthropic,
  DeepSeek,
  Google,
  Minimax,
  Moonshot,
  OpenAI,
  XAI,
  ZAI,
} from "@lobehub/icons";
import { PROVIDER_LABELS, type ProviderKey } from "../modelMeta";

// Thinking Machines Lab has no @lobehub/icons mark yet (checked 5.15.0), so
// this embeds the company's own 32px favicon (thinkingmachines.ai — their
// square mark) as an SVG mask filled with currentColor, keeping the canonical
// geometry while staying legible in both themes. Swap for the @lobehub icon
// once one ships.
const TML_FAVICON =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABEUlEQVRYR2NkAIJnz54FMTAyNQCZWkDMDBKjIfgLNPsaw/9/DVJSUusYn718GcTw7/9qoCATDS3FZvQ/BibGUMbnL15c/P+fQY/OloOtY2RkuMT47PmLP3QIdlz++wtywP+B8D3MTqwO+PHjB8PylWsYnr94SRW3SUqIM0SGhzBwcHBgmIfVAfMXLWVYs24DVSyHGRISFMCQGBdNnAPau/oYjhw7TlUH2FhZMlSWFY06YDQERkNgNARGQ2A0BEZDYDQEhkgIDHiT7Du0UfqCSo1SCWCjNIqURilVG4MEDBv4jsnAd82eATunjAPUOf0P7JyCogjSPWdsZGRk0vz//z9Nu+eMjIx/Gf7/v/Yf2j0HAN9HH5MVKknXAAAAAElFTkSuQmCC";

function ThinkingMachinesMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <mask id="tml-mark-mask">
        {/* Luminance mask: invert so the favicon's dark square (the mark
            itself) is what reveals currentColor, not the light tile
            around it. Transparent padding stays hidden either way. */}
        <image
          href={TML_FAVICON}
          width="32"
          height="32"
          filter="invert(1) contrast(5)"
        />
      </mask>
      <rect
        width="32"
        height="32"
        fill="currentColor"
        mask="url(#tml-mark-mask)"
      />
    </svg>
  );
}

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
      {provider === "alibaba" && <Alibaba.Color size={size} aria-hidden="true" />}
      {provider === "anthropic" && <Anthropic size={size} color="currentColor" aria-hidden="true" />}
      {provider === "deepseek" && <DeepSeek.Color size={size} aria-hidden="true" />}
      {provider === "google" && <Google.Color size={size} aria-hidden="true" />}
      {provider === "minimax" && <Minimax.Color size={size} aria-hidden="true" />}
      {provider === "moonshot" && <Moonshot size={size} color="currentColor" aria-hidden="true" />}
      {provider === "openai" && <OpenAI size={size} color="currentColor" aria-hidden="true" />}
      {provider === "thinkingmachines" && <ThinkingMachinesMark size={size} />}
      {provider === "xai" && <XAI size={size} color="currentColor" aria-hidden="true" />}
      {provider === "zai" && <ZAI size={size} color="currentColor" aria-hidden="true" />}
    </span>
  );
}
