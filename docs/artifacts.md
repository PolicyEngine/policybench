# Dashboard data artifacts

The dashboard payload (`data.json`, ~57MB) is a generated artifact, not
source. Committing each refresh as a repo blob bloats history, invites
lockfile-style merge conflicts, and — because the file is written by tooling —
leaves no gate between "an export produced something" and "the site ships it".
This contract closes that gap.

## The contract

Every write of a dashboard payload validates first:

- `policybench.dashboard_schema` checks the combined `{"countries": {...}}`
  shape, per-country required keys, scenario cross-references, and finite
  numbers. The most common historical failure — copying a per-country
  `<run>/<country>/data.json` to `app/src/data.json` — produces a specific,
  named error.
- Serialization uses `allow_nan=False`: Python's `json` will happily emit
  `NaN` literals that `JSON.parse` in the browser rejects.
- `policybench validate-dashboard [path]` checks any existing file.

The app applies the same shape guard at build time
(`app/src/lib/dataArtifact.ts`), so a bad payload fails the build with a
readable message instead of crashing the site at runtime.

## Publishing

```bash
policybench publish-dashboard --tag dashboard-data-YYYYMMDD
```

validates `app/src/data.json`, uploads it as a GitHub release asset, and
writes the committed pointer `app/src/data.artifact.json`:

```json
{
  "version": 1,
  "repo": "PolicyEngine/policybench",
  "tag": "dashboard-data-20260520",
  "asset": "dashboard-data.json",
  "url": "https://github.com/PolicyEngine/policybench/releases/download/...",
  "sha256": "...",
  "bytes": 57432435
}
```

Use a fresh tag per data refresh; the tag is the artifact's identity and the
sha256 is its integrity check. `--dry-run` validates and writes the pointer
without uploading.

## Consuming

`app/scripts/prepare-data.ts` resolves the payload in order:

1. `app/src/data.json` if present (local exports keep working unchanged), else
2. `app/src/data.artifact.json` — download the asset, verify its sha256,
   cache under `app/.cache/`, and refuse hash mismatches.

## Refresh flow (post-cutover)

`app/src/data.json` is no longer committed (and is gitignored); builds resolve
the pointer. A data refresh is:

1. Export the run locally (`policybench export-full-run` writes
   `app/src/data.json` in your working tree).
2. `policybench publish-dashboard --tag dashboard-data-<date>` — validates,
   uploads the release asset, rewrites the pointer.
3. Commit the pointer plus a snapshot-manifest update pinning the new
   artifact's sha256 (tests enforce pointer == manifest pin == the combined
   committed run exports).

`paper/snapshot/<date>/` copies stay committed and frozen — they are the
manuscript's evidence base, and the integrity tests rebuild the published
payload from them.

History rewriting to reclaim the existing ~250MB of data.json blobs is
intentionally out of scope: it would invalidate every open fork and PR, and
needs an explicit owner decision.
