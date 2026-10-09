/**
 * What the methodology copy says about the engine behind excluded outputs.
 * An excluded output keeps the value its exclusion was decided on, computed
 * with the engine version its record names (the payload's
 * referenceExclusions[].engineVersion), which can be older than the engine
 * behind the scored references.
 */
import type { ReferenceExclusion } from "../types";

/**
 * The live board's engine upgrade: excluded outputs whose value moves on the
 * new engine were re-reviewed and stay excluded. The count is the length of
 * the reference sidecar's engine_upgrade.excluded_outputs_rechecked, which the
 * payload does not carry; tests/test_disclosures.py checks both fields against
 * the frozen sidecar.
 */
export const ENGINE_UPGRADE_RECHECK = {
  engineVersion: "2.37.2",
  rechecked: 22,
};

function compareVersions(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/** Excluded outputs counted by the policyengine-us version of their value,
 * oldest version first. */
export function excludedOutputsByEngine(
  exclusions: ReferenceExclusion[],
): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const exclusion of exclusions) {
    const version = exclusion.engineVersion.replace(/^policyengine-us /, "");
    counts.set(version, (counts.get(version) ?? 0) + 1);
  }
  return [...counts.entries()].sort(([a], [b]) => compareVersions(a, b));
}

/**
 * "The 56 excluded outputs keep the values they were decided on (52 computed
 * with policyengine-us 1.755.4, 4 with 2.15.17), and PolicyBench re-reviewed
 * the 19 of them that move on 2.15.17; all 19 stay excluded."
 */
export function excludedOutputEngineSentence(
  exclusions: ReferenceExclusion[] | undefined,
  referenceEngineVersion: string | null,
): string | null {
  if (!exclusions || exclusions.length === 0) return null;
  const groups = excludedOutputsByEngine(exclusions).map(
    ([version, count], index) =>
      index === 0
        ? `${count.toLocaleString("en-US")} computed with policyengine-us ${version}`
        : `${count.toLocaleString("en-US")} with ${version}`,
  );
  let sentence = `The ${exclusions.length.toLocaleString("en-US")} excluded outputs keep the values they were decided on (${groups.join(", ")})`;
  if (referenceEngineVersion === ENGINE_UPGRADE_RECHECK.engineVersion) {
    const { rechecked, engineVersion } = ENGINE_UPGRADE_RECHECK;
    sentence += `, and PolicyBench re-reviewed the ${rechecked} of them that move on ${engineVersion}; all ${rechecked} stay excluded`;
  }
  return `${sentence}.`;
}
