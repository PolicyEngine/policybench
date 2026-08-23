"""Reasoning stability (stability spec layer 2).

When a model gives the same answer twice, does it cite the same mechanism
twice? The LLM judge here does one thing only: it maps a single explanation
text onto discrete mechanism labels drawn from the audit taxonomy. It never
sees a pair, never compares, never scores, and never does arithmetic.
Everything else — pairing, agreement, numeric-claim comparison, validation
statistics — is deterministic code (docs/stability_spec.md, layer 2).

Per the adversarial review, 12-label extraction is the Stability Trap
paper's Tier-2 semantic-classification regime, not its >90% verbatim
extraction regime; the validation battery (gold set, cross-judge
agreement, AC1/Krippendorff) carries the reliability claim.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations
from pathlib import Path

import litellm
import numpy as np
import pandas as pd

from policybench.analysis import row_hit_scores
from policybench.annotation_taxonomy import FAILURE_SUBTYPE_VALUES
from policybench.spec import output_group_id
from policybench.stability import run_pair_frame

JUDGE_PROMPT_VERSION = "2026-08-18-v1"
DEFAULT_JUDGE_MODEL = "gemini/gemini-3.7-flash"
DEFAULT_CROSS_JUDGE_MODEL = "gpt-5.4-mini"
DEFAULT_CONCURRENCY = 8
JUDGE_MAX_TOKENS = 200
MIN_STABLE_EXACT_PAIRS = 200
VALIDATION_SAMPLE_MODULUS = 10  # ~10% of unique texts, by key hash

MECHANISM_LABELS: tuple[str, ...] = tuple(
    label for label in FAILURE_SUBTYPE_VALUES if label != "missing_output"
)

# Pre-registered fallback if the judge fails its reliability gate.
SUPER_DOMAINS: dict[str, tuple[str, ...]] = {
    "income_and_deductions": (
        "taxable_income_or_deductions",
        "asset_resource",
        "period_annualization",
    ),
    "rates_and_phaseouts": ("thresholds_rates", "credit_phaseout"),
    "eligibility": (
        "categorical_eligibility",
        "age_disability",
        "household_unit_or_filing_status",
    ),
    "program_specific": ("health_coverage", "payroll_tax_base", "state_local_rule"),
    "other": ("other",),
}

LABEL_GLOSSARY: dict[str, str] = {
    "taxable_income_or_deductions": (
        "how taxable or countable income is built: deductions, exclusions, "
        "itemization, allowances, AGI construction"
    ),
    "credit_phaseout": (
        "a credit's amount, phase-in, phase-out, or refundability (EITC, CTC, "
        "state credits)"
    ),
    "thresholds_rates": (
        "a specific rate, bracket, threshold, poverty-line multiple, taper, "
        "or exemption amount applied to a quantity"
    ),
    "categorical_eligibility": (
        "a program's eligibility test or pathway: who qualifies, income or "
        "categorical tests, enrollment rules"
    ),
    "asset_resource": "asset, resource, savings, or capital limits and tests",
    "health_coverage": (
        "health coverage mechanics: premiums, Marketplace plans, "
        "employer-sponsored insurance, Medicaid/CHIP/Medicare coverage logic"
    ),
    "age_disability": (
        "age limits, disability or blindness status, Medicare age, child-age windows"
    ),
    "period_annualization": (
        "converting between monthly, weekly, and annual amounts or "
        "certification periods"
    ),
    "payroll_tax_base": (
        "payroll or self-employment tax: Social Security, Medicare, FICA, wage bases"
    ),
    "state_local_rule": (
        "a state or local rule, parameter, supplement, conformity election, "
        "or absence of a state tax"
    ),
    "household_unit_or_filing_status": (
        "filing status, dependents, household or unit composition, "
        "head-of-household or joint rules, deeming across members"
    ),
    "other": (
        "a mechanism that fits none of the above, or an explanation that "
        "names no mechanism"
    ),
}

# Few-shot anchors, verbatim from the committed reference-explanation CSV
# (annotations/us_full_run_20260612_policyengine_4_16_1_populace/
# us_case_reference_explanations.csv), labeled by the developers.
FEW_SHOT_EXAMPLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "payroll_tax",
        "PolicyEngine calculated the annual payroll tax for this single Texas "
        "resident at $229.50 by summing two components of the employee payroll "
        "tax. The employee Social Security tax contributed $186.00, which is "
        "calculated as 6.2% of the individual's covered wages up to the annual "
        "Social Security wage base. The employee Medicare tax added $43.50, "
        "computed at 1.45% of total wages with no wage cap. Since this "
        "individual is classified as a tax unit head, these employee-side "
        "payroll obligations were attributed directly to their tax liability "
        "for the 2026 tax year.",
        ("payroll_tax_base", "thresholds_rates"),
    ),
    (
        "snap",
        "PolicyEngine calculated a SNAP (Supplemental Nutrition Assistance "
        "Program) benefit of $0 for this Ohio household of two adults with no "
        "children and approximately $94,925 in annual household income. The "
        "household's income substantially exceeds the SNAP eligibility "
        "threshold for a two-person household in 2026, which is set at 130% "
        "of the federal poverty line. With this income level, the household "
        "does not qualify for any SNAP benefits under federal program rules, "
        "resulting in the zero benefit amount.",
        ("categorical_eligibility", "thresholds_rates"),
    ),
    (
        "child1_early_head_start_eligible",
        "PolicyEngine determined that neither child in this California "
        "household is eligible for Early Head Start in 2026, resulting in a "
        "value of False for both children. Early Head Start eligibility is "
        "typically restricted to children under age 3 from families with "
        "incomes at or below 100% of the federal poverty line or receiving "
        "public assistance. With a household income of approximately "
        "$159,676, this family's earnings substantially exceed the income "
        "threshold required for the program. Consequently, PolicyEngine "
        "assigned an eligibility status of False to each child, yielding the "
        "reference value of 0.0 for the household.",
        ("categorical_eligibility", "age_disability", "thresholds_rates"),
    ),
    (
        "ssi",
        "For this Ohio household in 2026, PolicyEngine calculated Supplemental "
        "Security Income (SSI) of $0.00 because neither household member meets "
        "SSI's eligibility criteria. The head of household, age 61, and the "
        "spouse, age 57, both have `is_ssi_aged_blind_disabled` set to False, "
        "meaning neither qualifies under SSI's three eligibility pathways: "
        "being age 65 or older, blind, or disabled. Since SSI eligibility is "
        "determined on an individual basis with spousal deeming rules applied "
        "per person rather than as a pooled household total, the absence of "
        "any qualifying member results in zero SSI benefits for the "
        "household.",
        (
            "categorical_eligibility",
            "age_disability",
            "household_unit_or_filing_status",
        ),
    ),
)

_USD_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)")
_WS_RE = re.compile(r"\s+")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _round_half_up(value: float, ndigits: int) -> float:
    """Round like a reader would (1.45 -> 1.5), not like float repr does."""
    quantum = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def normalize_explanation_text(text) -> str:
    """Casefold and collapse whitespace so trivially different texts match."""
    if text is None:
        return ""
    try:
        if pd.isna(text):
            return ""
    except (TypeError, ValueError):
        pass
    return _WS_RE.sub(" ", str(text)).strip().casefold()


def extract_numeric_claims(text, exclude_value: float | None = None) -> frozenset:
    """Deterministic numeric-claim channel: dollars (to $1) and percents (0.1pp).

    Values within $1 of ``exclude_value`` (the row's own prediction) are
    dropped — the restated answer would inflate overlap by construction.
    """
    normalized = normalize_explanation_text(text)
    if not normalized:
        return frozenset()
    claims = set()
    for match in _USD_RE.finditer(normalized):
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if exclude_value is not None and abs(value - float(exclude_value)) <= 1.0:
            continue
        claims.add(("usd", int(_round_half_up(value, 0))))
    for match in _PCT_RE.finditer(normalized):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        claims.add(("pct", _round_half_up(value, 1)))
    return frozenset(claims)


def text_key(variable: str, text) -> str:
    """Judge-independent identity of an explanation text for one variable."""
    payload = f"{JUDGE_PROMPT_VERSION}|{variable}|{normalize_explanation_text(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def judge_cache_key(judge_model: str, variable: str, text, grade_pass: int = 0) -> str:
    """Dedup key for one extraction call; grade_pass forces independent repeats."""
    payload = f"{judge_model}|{text_key(variable, text)}|{grade_pass}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_judge_prompt(
    text: str, variable: str, country: str = "us", year: int = 2026
) -> str:
    glossary = "\n".join(
        f"- {label}: {definition}" for label, definition in LABEL_GLOSSARY.items()
    )
    examples = "\n\n".join(
        f"Example (output: {example_variable})\nExplanation: {example_text}\n"
        f'Labels: {{"labels": {json.dumps(list(labels))}}}'
        for example_variable, example_text, labels in FEW_SHOT_EXAMPLES
    )
    return f"""You label the mechanisms that one tax/benefit explanation relies on.
Prompt version: {JUDGE_PROMPT_VERSION}

Read the single explanation below and list every mechanism label whose
definition matches something the explanation's stated derivation actually
rests on. Use only labels from this list:
{glossary}

Rules: label only what the text states, not what the correct derivation
would be; do not evaluate whether the explanation is right; do not
calculate anything; return strict JSON with one key "labels" holding a
list of label strings (an explanation that names no mechanism gets
["other"]).

{examples}

Now label this explanation.
Output: {variable} (country {country.upper()}, tax year {year})
Explanation: {text}
Labels:"""


def parse_judge_labels(content) -> list[str]:
    """Validate a judge response into a deduplicated list of taxonomy labels."""
    if content is None:
        raise ValueError("empty judge response")
    match = _JSON_OBJECT_RE.search(str(content))
    if not match:
        raise ValueError("invalid judge response: no JSON object found")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid judge response: {exc}") from exc
    labels = payload.get("labels") if isinstance(payload, dict) else None
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError("invalid judge response: 'labels' must be a list of strings")
    out: list[str] = []
    for label in labels:
        if label not in MECHANISM_LABELS:
            raise ValueError(f"invalid judge response: unknown label {label!r}")
        if label not in out:
            out.append(label)
    if not out:
        raise ValueError("invalid judge response: empty label list")
    return out


async def _extract_one(
    semaphore: asyncio.Semaphore,
    judge_model: str,
    item: dict,
) -> dict:
    prompt = build_judge_prompt(
        item["text"],
        item["variable"],
        item.get("country", "us"),
        item.get("year", 2026),
    )
    last_error = ""
    async with semaphore:
        for _attempt in range(2):
            try:
                response = await litellm.acompletion(
                    model=judge_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=JUDGE_MAX_TOKENS,
                    # Never the shared disk cache: validation re-grades must be
                    # independent calls, and identical texts are deduplicated
                    # by this module's own key instead.
                    caching=False,
                )
                content = response.choices[0].message.content
                labels = parse_judge_labels(content)
                return {"labels": labels, "error": "", "raw": str(content)}
            except ValueError as exc:
                last_error = str(exc)
            except Exception as exc:  # provider/transport failures
                last_error = f"{type(exc).__name__}: {exc}"
    return {"labels": None, "error": last_error or "invalid judge response", "raw": ""}


async def _extract_batch(
    items: list[dict], judge_model: str, concurrency: int
) -> list[dict]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    return await asyncio.gather(
        *(_extract_one(semaphore, judge_model, item) for item in items)
    )


def _read_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = record.get("key")
        if key:
            out[key] = record
    return out


def run_label_extraction(
    items: list[dict],
    judge_model: str,
    cache_path: str | Path,
    concurrency: int = DEFAULT_CONCURRENCY,
    grade_pass: int = 0,
) -> dict[str, dict]:
    """Extract mechanism labels for explanation items with disk dedup.

    ``items`` carry ``variable``, ``text`` and optionally ``country``/``year``.
    Returns ``{judge_cache_key: record}`` where a record has ``labels`` (list
    or None), ``error``, ``text_key``, ``variable``, ``judge_model``,
    ``prompt_version`` and ``grade_pass``. Identical normalized texts for one
    variable share one call; failed extractions are recorded (and retried on
    the next invocation) rather than cached as results.
    """
    cache_path = Path(cache_path)
    cache = _read_cache(cache_path)
    unique: dict[str, dict] = {}
    for item in items:
        key = judge_cache_key(judge_model, item["variable"], item["text"], grade_pass)
        unique.setdefault(key, item)
    todo = {key: item for key, item in unique.items() if key not in cache}
    if todo:
        keys = list(todo)
        results = asyncio.run(
            _extract_batch([todo[key] for key in keys], judge_model, concurrency)
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("a", encoding="utf-8") as handle:
            for key, result in zip(keys, results, strict=True):
                item = todo[key]
                record = {
                    "key": key,
                    "text_key": text_key(item["variable"], item["text"]),
                    "variable": item["variable"],
                    "judge_model": judge_model,
                    "prompt_version": JUDGE_PROMPT_VERSION,
                    "grade_pass": grade_pass,
                    "labels": result["labels"],
                    "error": result["error"],
                }
                cache[key] = record
                if result["labels"] is not None:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
    return {key: cache[key] for key in unique}


def labels_by_text_key_from_results(results: dict[str, dict]) -> dict[str, frozenset]:
    """Collapse extraction records into {text_key: label set} (errors dropped)."""
    return {
        record["text_key"]: frozenset(record["labels"])
        for record in results.values()
        if record.get("labels")
    }


def explanation_pair_frame(
    repeated_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> pd.DataFrame:
    """Run pairs with explanations, answer-stability strata, and text keys."""
    pairs = run_pair_frame(repeated_predictions, ground_truth)
    if pairs.empty:
        return pairs
    has_explanations = "explanation" in repeated_predictions.columns
    lookup = {
        (row.model, row.run_id, row.scenario_id, row.variable): (
            row.prediction,
            getattr(row, "explanation", None) if has_explanations else None,
        )
        for row in repeated_predictions.itertuples()
    }
    records = []
    for row in pairs.itertuples():
        pred_a, text_a = lookup.get(
            (row.model, row.run_a, row.scenario_id, row.variable), (None, None)
        )
        pred_b, text_b = lookup.get(
            (row.model, row.run_b, row.scenario_id, row.variable), (None, None)
        )
        norm_a = normalize_explanation_text(text_a)
        norm_b = normalize_explanation_text(text_b)
        stable = bool(row.both_parsed and row.mutually_exact)
        records.append(
            {
                "model": row.model,
                "scenario_id": row.scenario_id,
                "variable": row.variable,
                "output_group": output_group_id(row.variable),
                "run_a": row.run_a,
                "run_b": row.run_b,
                "stable": stable,
                "stable_exact": bool(stable and row.exact_a and row.exact_b),
                "prediction_a": pred_a,
                "prediction_b": pred_b,
                "explanation_a": text_a,
                "explanation_b": text_b,
                "has_explanations": bool(norm_a and norm_b),
                "verbatim_identical": bool(norm_a and norm_a == norm_b),
                "text_key_a": text_key(row.variable, text_a),
                "text_key_b": text_key(row.variable, text_b),
            }
        )
    return pd.DataFrame(records)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _rate(mask: pd.Series, values: pd.Series) -> float:
    selected = values[mask]
    return float(selected.mean()) if len(selected) else float("nan")


def reasoning_stability_by_model(
    pairs: pd.DataFrame,
    labels_by_text_key: dict[str, frozenset],
    pair_noise_floor: float | None = None,
    min_stable_exact_pairs: int = MIN_STABLE_EXACT_PAIRS,
) -> dict[str, pd.DataFrame]:
    """Per-model reasoning-stability metrics from judge labels.

    Verbatim-identical explanation pairs count as agreeing without a judge
    call; the share of stable pairs resolved that way is published because a
    model that repeats canned text incurs zero judge noise. Pairs lacking a
    label on either side (judge error, unjudged) are excluded from label
    rates and counted in ``n_unjudged_stable_pairs``.
    """
    if pairs.empty:
        return {"summary": pd.DataFrame(), "composition": pd.DataFrame()}
    frame = pairs.copy()
    labels_a = frame["text_key_a"].map(labels_by_text_key)
    labels_b = frame["text_key_b"].map(labels_by_text_key)
    frame["judged"] = frame["verbatim_identical"] | (
        labels_a.notna() & labels_b.notna()
    )
    same = []
    jaccard = []
    claim_jaccard = []
    claim_disjoint = []
    for row, la, lb in zip(frame.itertuples(), labels_a, labels_b, strict=True):
        if row.verbatim_identical:
            same.append(True)
            jaccard.append(1.0)
        elif isinstance(la, frozenset) and isinstance(lb, frozenset):
            same.append(la == lb)
            jaccard.append(_jaccard(la, lb))
        else:
            same.append(False)
            jaccard.append(float("nan"))
        claims_a = extract_numeric_claims(row.explanation_a, row.prediction_a)
        claims_b = extract_numeric_claims(row.explanation_b, row.prediction_b)
        claim_jaccard.append(_jaccard(claims_a, claims_b))
        claim_disjoint.append(bool(claims_a and claims_b and not (claims_a & claims_b)))
    frame["same_labels"] = same
    frame["label_jaccard"] = jaccard
    frame["claim_jaccard"] = claim_jaccard
    frame["claim_disjoint"] = claim_disjoint
    frame["divergent"] = frame["judged"] & ~frame["same_labels"]

    stable_exact_judged = frame[frame["stable_exact"] & frame["judged"]]
    composition_rows = []
    for (model, group), sub in stable_exact_judged.groupby(["model", "output_group"]):
        composition_rows.append(
            {
                "model": model,
                "output_group": group,
                "n_stable_exact_pairs": int(len(sub)),
                "unstable_reasoning_rate": float((~sub["same_labels"]).mean()),
            }
        )
    composition = pd.DataFrame(composition_rows)
    if not composition.empty:
        pooled = composition.groupby("output_group")["n_stable_exact_pairs"].sum()
        standard_weights = pooled / pooled.sum()
        composition = composition.merge(
            composition.groupby("model")["n_stable_exact_pairs"]
            .sum()
            .rename("model_total"),
            on="model",
        )
        composition["share_within_model"] = (
            composition["n_stable_exact_pairs"] / composition["model_total"]
        )
        composition = composition.drop(columns=["model_total"])
    else:
        standard_weights = pd.Series(dtype=float)

    rows = []
    for model, group in frame.groupby("model"):
        stable = group["stable"]
        stable_exact = group["stable_exact"]
        judged = group["judged"]
        verbatim = group["verbatim_identical"]
        n_judged_se = int((stable_exact & judged).sum())
        agreement_se = _rate(stable_exact & judged, group["same_labels"])
        headline = 1.0 - agreement_se if not math.isnan(agreement_se) else float("nan")
        nonidentical = _rate(stable_exact & judged & ~verbatim, ~group["same_labels"])
        adjusted = float("nan")
        if pair_noise_floor is not None and not math.isnan(headline):
            adjusted = max(
                0.0, (headline - pair_noise_floor) / (1.0 - pair_noise_floor)
            )
        standardized = float("nan")
        if not composition.empty:
            model_comp = composition[composition["model"] == model].set_index(
                "output_group"
            )
            if not model_comp.empty:
                weights = standard_weights.reindex(model_comp.index).fillna(0.0)
                if weights.sum() > 0:
                    standardized = float(
                        (model_comp["unstable_reasoning_rate"] * weights).sum()
                        / weights.sum()
                    )
        rows.append(
            {
                "model": model,
                "n_pairs_total": int(len(group)),
                "n_stable_pairs": int(stable.sum()),
                "n_stable_exact_pairs": int(stable_exact.sum()),
                "n_judged_stable_exact_pairs": n_judged_se,
                "n_unjudged_stable_pairs": int((stable & ~judged).sum()),
                "short_circuit_share_stable": _rate(stable, verbatim),
                "mechanism_agreement_rate_stable": _rate(
                    stable & judged, group["same_labels"]
                ),
                "mechanism_agreement_rate_stable_exact": agreement_se,
                "right_answer_unstable_reasoning_rate": headline,
                "right_answer_unstable_reasoning_rate_nonidentical": nonidentical,
                "right_answer_unstable_reasoning_rate_adjusted": adjusted,
                "joint_unstable_reasoning_rate_all_pairs": float(
                    (stable_exact & group["divergent"]).sum() / len(group)
                ),
                "standardized_unstable_reasoning_rate": standardized,
                "mechanism_jaccard_mean_stable": _rate(
                    stable & judged, group["label_jaccard"]
                ),
                "mechanism_jaccard_mean_stable_exact": _rate(
                    stable_exact & judged, group["label_jaccard"]
                ),
                "numeric_claim_jaccard_mean_stable_exact": _rate(
                    stable_exact, group["claim_jaccard"]
                ),
                "numeric_claim_disjoint_rate_stable_exact": _rate(
                    stable_exact, group["claim_disjoint"]
                ),
                "reasoning_unstable_strict_rate": _rate(
                    stable_exact & judged,
                    ~group["same_labels"] | group["claim_disjoint"],
                ),
                "headline_suppressed": n_judged_se < min_stable_exact_pairs,
            }
        )
    return {"summary": pd.DataFrame(rows), "composition": composition}


def reference_alignment_by_model(
    repeated_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
    labels_by_text_key: dict[str, frozenset],
    reference_labels: dict[tuple[str, str], frozenset],
) -> pd.DataFrame:
    """Among exact-correct run-explanations, share whose labels match the anchor."""
    truth = ground_truth.set_index(["scenario_id", "variable"])["value"]
    rows = []
    for model, group in repeated_predictions.groupby("model"):
        n_exact = 0
        n_labeled = 0
        n_aligned = 0
        for row in group.itertuples():
            key = (row.scenario_id, row.variable)
            if key not in truth.index:
                continue
            if not row_hit_scores(row.variable, truth[key], row.prediction)["exact"]:
                continue
            n_exact += 1
            labels = labels_by_text_key.get(
                text_key(row.variable, getattr(row, "explanation", None))
            )
            anchor = reference_labels.get(key)
            if labels is None or anchor is None:
                continue
            n_labeled += 1
            n_aligned += int(labels == anchor)
        rows.append(
            {
                "model": model,
                "n_exact_rows": n_exact,
                "n_exact_labeled": n_labeled,
                "reference_alignment_rate": (
                    n_aligned / n_labeled if n_labeled else float("nan")
                ),
            }
        )
    return pd.DataFrame(rows)


# --- validation statistics -------------------------------------------------


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = successes / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    if not a or len(a) != len(b):
        return float("nan")
    a_arr = np.asarray(a, dtype=bool)
    b_arr = np.asarray(b, dtype=bool)
    pa = float((a_arr == b_arr).mean())
    pa_pos, pb_pos = float(a_arr.mean()), float(b_arr.mean())
    pe = pa_pos * pb_pos + (1 - pa_pos) * (1 - pb_pos)
    if pe >= 1.0:
        return float("nan")
    return (pa - pe) / (1 - pe)


def gwet_ac1(a: list[bool], b: list[bool]) -> float:
    """Gwet's AC1 for two raters on a binary label (prevalence-robust)."""
    if not a or len(a) != len(b):
        return float("nan")
    a_arr = np.asarray(a, dtype=bool)
    b_arr = np.asarray(b, dtype=bool)
    pa = float((a_arr == b_arr).mean())
    pi = (float(a_arr.mean()) + float(b_arr.mean())) / 2.0
    pe = 2.0 * pi * (1.0 - pi)
    if pe >= 1.0:
        return float("nan")
    return (pa - pe) / (1 - pe)


def krippendorff_alpha_jaccard(
    set_pairs: list[tuple[frozenset, frozenset]], max_pooled: int = 2000, seed: int = 0
) -> float:
    """Krippendorff's alpha for two coders over label sets, Jaccard distance."""
    if not set_pairs:
        return float("nan")
    observed = float(np.mean([1.0 - _jaccard(a, b) for a, b in set_pairs]))
    pooled = [s for pair in set_pairs for s in pair]
    if len(pooled) > max_pooled:
        rng = np.random.default_rng(seed)
        pooled = [pooled[i] for i in rng.choice(len(pooled), max_pooled, replace=False)]
    distances = [1.0 - _jaccard(x, y) for x, y in combinations(pooled, 2)]
    expected = float(np.mean(distances)) if distances else 0.0
    if expected == 0.0:
        return 1.0 if observed == 0.0 else float("nan")
    return 1.0 - observed / expected


def dominant_set_share(label_sets: list[frozenset]) -> float:
    """Share of runs agreeing with the modal label set (the R_stab analogue)."""
    if not label_sets:
        return float("nan")
    counts: dict[frozenset, int] = {}
    for s in label_sets:
        counts[s] = counts.get(s, 0) + 1
    return max(counts.values()) / len(label_sets)


def evaluate_against_gold(
    gold: pd.DataFrame,
    labels_by_key: dict[str, frozenset],
    judge_model: str,
    grade_pass: int = 0,
) -> dict:
    """Judge-vs-gold exact-set accuracy (Wilson CI) and per-label agreement.

    ``gold`` has columns ``variable``, ``explanation``, ``labels`` (pipe-
    separated taxonomy labels); ``labels_by_key`` is keyed by judge cache key.
    """
    matches = []
    judge_sets: list[frozenset] = []
    gold_sets: list[frozenset] = []
    for row in gold.itertuples():
        key = judge_cache_key(judge_model, row.variable, row.explanation, grade_pass)
        judged = labels_by_key.get(key)
        if judged is None:
            continue
        gold_set = frozenset(
            label.strip() for label in str(row.labels).split("|") if label.strip()
        )
        judge_sets.append(frozenset(judged))
        gold_sets.append(gold_set)
        matches.append(frozenset(judged) == gold_set)
    n_graded = len(matches)
    accuracy = float(np.mean(matches)) if matches else float("nan")
    ci_low, ci_high = wilson_ci(int(sum(matches)), n_graded)
    per_label_rows = []
    for label in MECHANISM_LABELS:
        judge_flags = [label in s for s in judge_sets]
        gold_flags = [label in s for s in gold_sets]
        per_label_rows.append(
            {
                "label": label,
                "gold_positives": int(sum(gold_flags)),
                "judge_positives": int(sum(judge_flags)),
                "agreement": (
                    float(
                        np.mean(
                            [
                                g == j
                                for g, j in zip(gold_flags, judge_flags, strict=True)
                            ]
                        )
                    )
                    if n_graded
                    else float("nan")
                ),
                "gwet_ac1": gwet_ac1(gold_flags, judge_flags),
            }
        )
    return {
        "judge_model": judge_model,
        "n_gold": int(len(gold)),
        "n_graded": n_graded,
        "exact_set_accuracy": accuracy,
        "exact_set_accuracy_ci_low": ci_low,
        "exact_set_accuracy_ci_high": ci_high,
        "krippendorff_alpha_jaccard": krippendorff_alpha_jaccard(
            list(zip(gold_sets, judge_sets, strict=True))
        ),
        "per_label": pd.DataFrame(per_label_rows),
    }


def validation_sample_keys(
    text_keys: list[str], modulus: int = VALIDATION_SAMPLE_MODULUS
) -> list[str]:
    """Deterministic ~1/modulus sample of unique texts for re-grading."""
    return [key for key in sorted(set(text_keys)) if int(key[:8], 16) % modulus == 0]


def pair_agreement_summary(
    primary: dict[str, frozenset],
    secondary: dict[str, frozenset],
) -> dict:
    """Set agreement, noise floor, AC1/alpha/kappa over texts graded by both."""
    keys = sorted(set(primary) & set(secondary))
    if not keys:
        return {"n": 0, "set_agreement": float("nan"), "pair_noise_floor": float("nan")}
    pairs = [(primary[k], secondary[k]) for k in keys]
    agree = [a == b for a, b in pairs]
    n = len(keys)
    agreement = float(np.mean(agree))
    ci_low, ci_high = wilson_ci(int(sum(agree)), n)
    per_label = []
    for label in MECHANISM_LABELS:
        a_flags = [label in a for a, _ in pairs]
        b_flags = [label in b for _, b in pairs]
        occurrences = int(sum(a_flags) + sum(b_flags))
        per_label.append(
            {
                "label": label,
                "prevalence": occurrences / (2 * n),
                "raw_agreement": float(
                    np.mean([x == y for x, y in zip(a_flags, b_flags, strict=True)])
                ),
                "gwet_ac1": gwet_ac1(a_flags, b_flags),
                "cohen_kappa": cohen_kappa(a_flags, b_flags)
                if occurrences >= 20
                else float("nan"),
            }
        )
    return {
        "n": n,
        "set_agreement": agreement,
        "set_agreement_ci_low": ci_low,
        "set_agreement_ci_high": ci_high,
        "pair_noise_floor": 1.0 - agreement,
        "krippendorff_alpha_jaccard": krippendorff_alpha_jaccard(pairs),
        "per_label": pd.DataFrame(per_label),
    }
