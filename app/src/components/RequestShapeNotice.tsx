import { isCurrentBoard } from "../lib/boardScope";
import { MODEL_LABELS } from "../modelMeta";

export function outputCountFromRequestShape(
  requestShape: string | undefined,
): number | null {
  const match = requestShape?.match(/^(\d+) outputs?\/request$/);
  return match ? Number(match[1]) : null;
}

export default function RequestShapeNotice({
  model,
  requestShape,
  versionId,
  liveVersionId,
}: {
  model: string;
  requestShape: string | undefined;
  versionId: string;
  liveVersionId: string;
}) {
  if (!isCurrentBoard(versionId, liveVersionId)) return null;

  const outputCount = outputCountFromRequestShape(requestShape);
  if (outputCount === null) return null;

  return (
    <p className="mt-3 text-xs text-text-muted leading-relaxed">
      {MODEL_LABELS[model] ?? model} answered this household over {outputCount}
      -output subsets of this prompt; the per-model request shape is in the
      paper&apos;s serving-configuration table.
    </p>
  );
}
