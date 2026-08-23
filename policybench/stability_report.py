"""Command implementations for the stability suite (docs/stability_spec.md).

``policybench stability-report``, ``reasoning-stability``,
``counterfactual-manifest``, ``counterfactual-report`` and
``stability-cost-plan`` dispatch here. Each export directory carries a
``stability_metadata.json`` with the provenance the spec requires.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path

import pandas as pd

from policybench.analysis import (
    run_stability_by_model,
    summarize_runs_by_model,
    usage_summary_by_model,
)
from policybench.config import MODELS, PRICE_OVERRIDES_PER_1M
from policybench.counterfactual import (
    CF_DEFAULT_AMOUNT,
    build_counterfactual_manifest,
    compute_truth_deltas,
    delta_metrics_by_model,
    matched_delta_frame,
    noise_floor_frame,
    signal_vs_noise_test,
)
from policybench.model_cards import (
    PROMPT_CONTRACT_VERSION,
    answer_contract_for,
    explanation_chunk_size_for,
)
from policybench.reasoning_stability import (
    DEFAULT_CROSS_JUDGE_MODEL,
    DEFAULT_JUDGE_MODEL,
    JUDGE_PROMPT_VERSION,
    MIN_STABLE_EXACT_PAIRS,
    dominant_set_share,
    evaluate_against_gold,
    explanation_pair_frame,
    labels_by_text_key_from_results,
    pair_agreement_summary,
    reasoning_stability_by_model,
    reference_alignment_by_model,
    run_label_extraction,
    text_key,
    validation_sample_keys,
)
from policybench.stability import (
    STABILITY_SPEC_VERSION,
    assert_cache_free,
    cross_run_response_id_duplicates,
    load_runs_dirs,
    row_stability_by_model,
    stability_variance_decomposition,
)

DEFAULT_SERVING_CONFIG = Path("paper/snapshot/20260501/model_serving_config.json")
DEFAULT_GOLD_SET = Path("annotations/stability_reasoning_gold_set.csv")

GOLD_ACCURACY_GATE = 0.80
GOLD_ACCURACY_CI_FLOOR = 0.70
CROSS_JUDGE_AGREEMENT_GATE = 0.90


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _installed_version(package: str) -> str | None:
    try:
        return importlib_metadata.version(package)
    except importlib_metadata.PackageNotFoundError:
        return None


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, float) and value != value:  # NaN
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (ValueError, TypeError):
            return str(value)
    return value


def write_metadata(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "stability_metadata.json"
    base = {
        "stability_spec_version": STABILITY_SPEC_VERSION,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "generated_at": _now(),
        "installed_policyengine_us": _installed_version("policyengine-us"),
        "installed_policyengine": _installed_version("policyengine"),
    }
    base.update(payload)
    path.write_text(
        json.dumps(_json_safe(base), indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def _write_tables(output_dir: Path, tables: dict[str, pd.DataFrame]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, frame in tables.items():
        if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty):
            continue
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        written[name] = str(path)
    return written


def read_runs_metadata(runs_dirs: list[str | Path]) -> dict:
    """Load runs_metadata.json sidecars and check they agree on the fingerprint."""
    sidecars = {}
    for runs_dir in runs_dirs:
        path = Path(runs_dir) / "runs_metadata.json"
        sidecars[str(runs_dir)] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        )
    present = {k: v for k, v in sidecars.items() if v is not None}
    missing = [k for k, v in sidecars.items() if v is None]
    mismatches = []
    if len(present) > 1:
        reference_key, reference = next(iter(present.items()))
        for key, value in present.items():
            for field in ("scenario_hash", "programs", "response_contract", "repeats"):
                if value.get(field) != reference.get(field):
                    mismatches.append({"field": field, "a": reference_key, "b": key})
    if mismatches:
        raise ValueError(
            "runs directories disagree on repeat-set fingerprints; refusing to "
            f"pool: {mismatches}"
        )
    condition = None
    if present:
        contract = next(iter(present.values())).get("response_contract") or {}
        condition = {
            "tool_choice_condition": contract.get("tool_choice_condition"),
            "chunk_override": contract.get("chunk_override"),
        }
    return {
        "sidecars_present": sorted(present),
        "sidecars_missing": missing,
        "condition": condition,
        "cache_enabled_flags": {k: v.get("cache_enabled") for k, v in present.items()},
    }


def serving_config_diff(
    models: list[str],
    condition: dict | None,
    serving_config_path: str | Path | None,
) -> dict:
    """Diff each model's effective serving treatment against the board registry."""
    registry = {}
    path = Path(serving_config_path) if serving_config_path else None
    if path is not None and path.exists():
        registry = (json.loads(path.read_text(encoding="utf-8")) or {}).get(
            "models", {}
        )
    chunk_override = (condition or {}).get("chunk_override")
    tool_choice_condition = (condition or {}).get("tool_choice_condition") or "forced"
    out = {}
    for model in models:
        litellm_id = MODELS.get(model, model)
        contract = answer_contract_for(litellm_id)
        chunk = explanation_chunk_size_for(litellm_id, chunk_override=chunk_override)
        effective = {
            "answer_contract": contract,
            "request_shape": (
                f"{chunk} output{'s' if chunk != 1 else ''}/request"
                if chunk
                else "whole scenario"
            ),
            "tool_choice": tool_choice_condition if contract == "tool" else None,
        }
        snapshot = registry.get(model)
        diffs = {}
        if snapshot:
            for field, value in effective.items():
                if snapshot.get(field) != value:
                    diffs[field] = {"effective": value, "snapshot": snapshot.get(field)}
        out[model] = {
            "effective": effective,
            "in_snapshot_registry": snapshot is not None,
            "diffs": diffs,
        }
    return out


def _market_income(manifest: pd.DataFrame) -> dict[str, float]:
    if manifest is None or manifest.empty or "total_income" not in manifest.columns:
        return {}
    return dict(
        zip(
            manifest["scenario_id"].astype(str),
            pd.to_numeric(manifest["total_income"], errors="coerce").fillna(0.0),
            strict=True,
        )
    )


def _country(manifest: pd.DataFrame) -> str | None:
    if manifest is None or manifest.empty or "country" not in manifest.columns:
        return None
    values = manifest["country"].dropna().unique()
    return str(values[0]).lower() if len(values) == 1 else None


def run_stability_report(
    *,
    runs_dirs: list[str | Path],
    reference_outputs: str | Path,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    n_boot: int = 1000,
    seed: int = 20260818,
    serving_config: str | Path | None = DEFAULT_SERVING_CONFIG,
) -> dict:
    """Layer 1: answer-stability export with the cache guard enforced."""
    output_path = Path(output_dir)
    cache_report = assert_cache_free(runs_dirs)
    runs_meta = read_runs_metadata(runs_dirs)
    repeated = load_runs_dirs(runs_dirs)
    ground_truth = pd.read_csv(reference_outputs)
    manifest = pd.read_csv(scenario_manifest)
    market_income = _market_income(manifest)
    country = _country(manifest)

    run_model_summary = summarize_runs_by_model(ground_truth, repeated)
    tables = {
        "run_model_summary": run_model_summary,
        "run_stability_by_model": run_stability_by_model(run_model_summary),
        "row_stability_by_model": row_stability_by_model(
            repeated, ground_truth, n_boot=n_boot, seed=seed
        ),
    }
    per_model, pooled = stability_variance_decomposition(
        ground_truth, repeated, market_income, country=country
    )
    tables["variance_decomposition_by_model"] = per_model
    models = sorted(repeated["model"].dropna().unique())
    written = _write_tables(output_path, tables)
    metadata = {
        "layer": "answer_stability",
        "runs_dirs": [str(d) for d in runs_dirs],
        "models": models,
        "run_ids": sorted(repeated["run_id"].dropna().unique()),
        "reference_outputs": str(reference_outputs),
        "scenario_manifest": str(scenario_manifest),
        "cache_guard": cache_report,
        "cross_run_response_id_duplicates": cross_run_response_id_duplicates(repeated),
        "runs_metadata": runs_meta,
        "serving_config_diff": serving_config_diff(
            models, runs_meta.get("condition"), serving_config
        ),
        "pooled_variance_decomposition": pooled,
        "bootstrap": {"n_boot": n_boot, "seed": seed},
        "tables": written,
    }
    write_metadata(output_path, metadata)
    return {"tables": tables, "pooled": pooled, "metadata": metadata}


def run_counterfactual_manifest(
    *,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    programs: list[str],
    year: int,
    amount: float = CF_DEFAULT_AMOUNT,
    compute_references: bool = True,
    frozen_reference_outputs: str | Path | None = None,
) -> dict:
    """Layer 3 setup: twin manifest, both-arm references, truth deltas."""
    from policybench.scenarios import load_scenarios_from_manifest

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    base = load_scenarios_from_manifest(scenario_manifest)
    twins, manifest = build_counterfactual_manifest(base, amount)
    manifest_path = output_path / "cf_scenarios.csv"
    manifest.to_csv(manifest_path, index=False)
    metadata: dict = {
        "layer": "counterfactual",
        "scenario_manifest": str(scenario_manifest),
        "perturbation": {
            "field": "employment_income",
            "person": "adults[0]",
            "amount": float(amount),
            "n_scenarios": len(base),
            "n_first_dollar": int(manifest["first_dollar"].sum()),
        },
        "cf_scenarios": str(manifest_path),
        "programs": list(programs),
        "year": year,
    }
    if compute_references:
        deltas = compute_truth_deltas(base, twins, programs, year)
        deltas_path = output_path / "truth_deltas.csv"
        deltas.to_csv(deltas_path, index=False)
        amount_rows = deltas[~deltas["is_binary"]]
        nonzero = amount_rows[amount_rows["true_delta"].abs() > 1.0]
        metadata["truth_deltas"] = str(deltas_path)
        metadata["truth_delta_summary"] = {
            "n_rows": int(len(deltas)),
            "n_binary_rows": int(deltas["is_binary"].sum()),
            "n_binary_flips": int(
                (deltas["is_binary"] & (deltas["true_delta"].abs() > 0)).sum()
            ),
            "n_amount_rows": int(len(amount_rows)),
            "n_nonzero_amount_rows": int(len(nonzero)),
            "zero_delta_share": float((deltas["true_delta"].abs() <= 1.0).mean()),
            "n_positive": int((nonzero["true_delta"] > 0).sum()),
            "n_negative": int((nonzero["true_delta"] < 0).sum()),
            "nonzero_by_group": nonzero.groupby("output_group").size().to_dict(),
        }
        if frozen_reference_outputs and Path(frozen_reference_outputs).exists():
            frozen = pd.read_csv(frozen_reference_outputs)
            merged = deltas.merge(frozen, on=["scenario_id", "variable"], how="inner")
            drift = (merged["base_value"] - merged["value"]).abs()
            metadata["base_vs_frozen_reference_drift"] = {
                "frozen_reference_outputs": str(frozen_reference_outputs),
                "n_compared": int(len(merged)),
                "n_within_1usd": int((drift <= 1.0).sum()),
                "max_abs_drift": float(drift.max()) if len(drift) else None,
            }
    write_metadata(output_path, metadata)
    return metadata


def _fingerprint_summary(frame: pd.DataFrame) -> dict:
    out = {}
    for column in ("provider_resolved_model", "provider_system_fingerprint"):
        if column in frame.columns:
            out[column] = (
                frame.dropna(subset=[column])
                .groupby("model")[column]
                .nunique()
                .to_dict()
            )
    return out


def run_counterfactual_report(
    *,
    perturbed_predictions: str | Path,
    truth_deltas: str | Path,
    output_dir: str | Path,
    base_predictions: str | Path | None = None,
    base_runs_dirs: list[str | Path] | None = None,
    n_boot: int = 1000,
    seed: int = 20260818,
) -> dict:
    """Layer 3 analysis: delta metrics, baseline, noise floor, fingerprints."""
    output_path = Path(output_dir)
    if base_runs_dirs:
        cache_report = assert_cache_free(base_runs_dirs)
        base = load_runs_dirs(base_runs_dirs)
    elif base_predictions:
        cache_report = None
        base = pd.read_csv(base_predictions)
    else:
        raise ValueError("provide base_predictions or base_runs_dirs")
    perturbed = pd.read_csv(perturbed_predictions)
    truth = pd.read_csv(truth_deltas)
    matched = matched_delta_frame(base, perturbed, truth)
    tables = delta_metrics_by_model(matched)
    tables = {f"delta_{name}": frame for name, frame in tables.items()}
    metadata: dict = {
        "layer": "counterfactual",
        "perturbed_predictions": str(perturbed_predictions),
        "truth_deltas": str(truth_deltas),
        "base_predictions": str(base_predictions) if base_predictions else None,
        "base_runs_dirs": [str(d) for d in (base_runs_dirs or [])],
        "cache_guard": cache_report,
        "n_matched_rows": int(len(matched)),
        "provider_fingerprints": {
            "base": _fingerprint_summary(base),
            "perturbed": _fingerprint_summary(perturbed),
        },
    }
    if "provider_system_fingerprint" in base.columns and (
        "provider_system_fingerprint" in perturbed.columns
    ):
        pert = perturbed.copy()
        pert["scenario_id"] = pert["scenario_id"].str.replace("__cf1k", "", regex=False)
        joined = base.merge(
            pert[["model", "scenario_id", "variable", "provider_system_fingerprint"]],
            on=["model", "scenario_id", "variable"],
            suffixes=("_base", "_perturbed"),
        ).dropna(
            subset=[
                "provider_system_fingerprint_base",
                "provider_system_fingerprint_perturbed",
            ]
        )
        metadata["fingerprint_mismatched_pairs"] = int(
            (
                joined["provider_system_fingerprint_base"]
                != joined["provider_system_fingerprint_perturbed"]
            ).sum()
        )
    if "run_id" in base.columns and base["run_id"].nunique() >= 2:
        floor = noise_floor_frame(base, truth)
        floor_tables = delta_metrics_by_model(floor)
        tables["noise_floor_summary"] = floor_tables["summary"]
        tables["signal_vs_noise"] = signal_vs_noise_test(
            matched, floor, n_boot=n_boot, seed=seed
        )
    written = _write_tables(output_path, tables)
    metadata["tables"] = written
    write_metadata(output_path, metadata)
    return {"tables": tables, "metadata": metadata}


def _gate(
    point: float, ci_low: float, threshold: float, ci_floor: float | None = None
) -> dict:
    if point != point:  # NaN
        return {"status": "not_evaluated", "point": None, "threshold": threshold}
    if point < threshold or (ci_floor is not None and ci_low < ci_floor):
        status = "fail"
    elif ci_low < threshold:
        status = "pass_marginal"
    else:
        status = "pass"
    return {"status": status, "point": point, "ci_low": ci_low, "threshold": threshold}


def run_reasoning_stability(
    *,
    runs_dirs: list[str | Path],
    reference_outputs: str | Path,
    output_dir: str | Path,
    reference_explanations: str | Path | None = None,
    gold_set: str | Path | None = DEFAULT_GOLD_SET,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    cross_judge_model: str | None = DEFAULT_CROSS_JUDGE_MODEL,
    cache_dir: str | Path | None = None,
    deterministic_only: bool = False,
    concurrency: int = 8,
    validation_modulus: int = 10,
    min_stable_exact_pairs: int = MIN_STABLE_EXACT_PAIRS,
    country: str = "us",
    year: int = 2026,
) -> dict:
    """Layer 2: pair construction, judge extraction, validation, metrics."""
    output_path = Path(output_dir)
    cache_path = Path(cache_dir) if cache_dir else output_path / "judge_cache"
    cache_report = assert_cache_free(runs_dirs)
    runs_meta = read_runs_metadata(runs_dirs)
    repeated = load_runs_dirs(runs_dirs)
    ground_truth = pd.read_csv(reference_outputs)
    pairs = explanation_pair_frame(repeated, ground_truth)

    metadata: dict = {
        "layer": "reasoning_stability",
        "runs_dirs": [str(d) for d in runs_dirs],
        "cache_guard": cache_report,
        "runs_metadata": runs_meta,
        "judge": {
            "prompt_version": JUDGE_PROMPT_VERSION,
            "judge_model": None if deterministic_only else judge_model,
            "cross_judge_model": None if deterministic_only else cross_judge_model,
            "deterministic_only": deterministic_only,
        },
        "min_stable_exact_pairs": min_stable_exact_pairs,
    }
    labels: dict[str, frozenset] = {}
    reference_labels: dict[tuple[str, str], frozenset] = {}
    pair_noise_floor = None
    validation: dict = {}

    if not deterministic_only:
        explanation_items = []
        seen = set()
        if "explanation" in repeated.columns:
            for row in repeated.dropna(subset=["explanation"]).itertuples():
                key = text_key(row.variable, row.explanation)
                if key in seen:
                    continue
                seen.add(key)
                explanation_items.append(
                    {
                        "variable": row.variable,
                        "country": country,
                        "year": year,
                        "text": row.explanation,
                    }
                )
        primary = run_label_extraction(
            explanation_items, judge_model, cache_path / "primary.jsonl", concurrency
        )
        labels = labels_by_text_key_from_results(primary)
        metadata["judge"]["n_unique_texts"] = len(explanation_items)
        metadata["judge"]["n_judge_errors"] = sum(
            1 for r in primary.values() if r.get("labels") is None
        )

        if reference_explanations and Path(reference_explanations).exists():
            ref = pd.read_csv(reference_explanations)
            ref = ref[ref["explanation"].fillna("").str.strip() != ""]
            ref_items = [
                {
                    "variable": r.variable,
                    "country": country,
                    "year": year,
                    "text": r.explanation,
                }
                for r in ref.itertuples()
            ]
            ref_results = run_label_extraction(
                ref_items, judge_model, cache_path / "reference.jsonl", concurrency
            )
            ref_labels = labels_by_text_key_from_results(ref_results)
            for r in ref.itertuples():
                value = ref_labels.get(text_key(r.variable, r.explanation))
                if value is not None:
                    reference_labels[(r.scenario_id, r.variable)] = value
            metadata["judge"]["n_reference_anchors"] = len(reference_labels)

        # Validation battery.
        sample_keys = set(
            validation_sample_keys(
                [text_key(i["variable"], i["text"]) for i in explanation_items],
                modulus=validation_modulus,
            )
        )
        sample_items = [
            i
            for i in explanation_items
            if text_key(i["variable"], i["text"]) in sample_keys
        ]
        primary_sample = {
            r["text_key"]: frozenset(r["labels"])
            for r in primary.values()
            if r.get("labels") and r["text_key"] in sample_keys
        }
        if cross_judge_model and sample_items:
            cross = run_label_extraction(
                sample_items, cross_judge_model, cache_path / "cross.jsonl", concurrency
            )
            cross_summary = pair_agreement_summary(
                primary_sample, labels_by_text_key_from_results(cross)
            )
            pair_noise_floor = cross_summary.get("pair_noise_floor")
            validation["cross_judge"] = cross_summary
            validation["cross_judge_gate"] = _gate(
                cross_summary.get("set_agreement", float("nan")),
                cross_summary.get("set_agreement_ci_low", float("nan")),
                CROSS_JUDGE_AGREEMENT_GATE,
            )
        if sample_items:
            repeat = run_label_extraction(
                sample_items,
                judge_model,
                cache_path / "primary_pass1.jsonl",
                concurrency,
                grade_pass=1,
            )
            validation["determinism_floor"] = pair_agreement_summary(
                primary_sample, labels_by_text_key_from_results(repeat)
            )
        if gold_set and Path(gold_set).exists():
            gold = pd.read_csv(gold_set)
            gold_items = [
                {
                    "variable": r.variable,
                    "country": country,
                    "year": year,
                    "text": r.explanation,
                }
                for r in gold.itertuples()
            ]
            gold_results = run_label_extraction(
                gold_items, judge_model, cache_path / "gold.jsonl", concurrency
            )
            gold_labels = {
                key: frozenset(r["labels"])
                for key, r in gold_results.items()
                if r.get("labels")
            }
            gold_eval = evaluate_against_gold(gold, gold_labels, judge_model)
            validation["gold"] = gold_eval
            validation["gold_gate"] = _gate(
                gold_eval["exact_set_accuracy"],
                gold_eval["exact_set_accuracy_ci_low"],
                GOLD_ACCURACY_GATE,
                ci_floor=GOLD_ACCURACY_CI_FLOOR,
            )
        failed = [
            name
            for name in ("gold_gate", "cross_judge_gate")
            if validation.get(name, {}).get("status") == "fail"
        ]
        validation["judge_below_reliability_bar"] = bool(failed)
        validation["failed_gates"] = failed

    result = reasoning_stability_by_model(
        pairs,
        labels,
        pair_noise_floor=pair_noise_floor,
        min_stable_exact_pairs=min_stable_exact_pairs,
    )
    tables = {
        "reasoning_stability_by_model": result["summary"],
        "reasoning_stability_composition": result["composition"],
    }
    if reference_labels:
        tables["reference_alignment_by_model"] = reference_alignment_by_model(
            repeated, ground_truth, labels, reference_labels
        )
    if labels and "explanation" in repeated.columns:
        rows = []
        for (model, scenario_id, variable), group in repeated.groupby(
            ["model", "scenario_id", "variable"]
        ):
            sets = [
                labels.get(text_key(variable, e))
                for e in group["explanation"]
                if isinstance(e, str) and e.strip()
            ]
            sets = [s for s in sets if s is not None]
            if len(sets) >= 2:
                rows.append(
                    {
                        "model": model,
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "k_labeled": len(sets),
                        "dominant_set_share": dominant_set_share(sets),
                    }
                )
        if rows:
            dominant = pd.DataFrame(rows)
            tables["dominant_label_set_share_rows"] = dominant
            tables["dominant_label_set_share_by_model"] = (
                dominant.groupby("model")["dominant_set_share"]
                .mean()
                .rename("mean_dominant_set_share")
                .reset_index()
            )
    if not result["summary"].empty and validation.get("judge_below_reliability_bar"):
        result["summary"]["judge_below_reliability_bar"] = True
        result["summary"]["right_answer_unstable_reasoning_rate"] = float("nan")
    written = _write_tables(output_path, tables)
    for name, value in list(validation.items()):
        if isinstance(value, dict) and isinstance(value.get("per_label"), pd.DataFrame):
            per_label = value.pop("per_label")
            per_label.to_csv(
                output_path / f"validation_{name}_per_label.csv", index=False
            )
    metadata["validation"] = validation
    metadata["tables"] = written
    write_metadata(output_path, metadata)
    return {"tables": tables, "validation": validation, "metadata": metadata}


def stability_cost_plan(
    predictions: pd.DataFrame,
    *,
    repeats: int = 3,
    cf_arms: int = 1,
    models: list[str] | None = None,
    judge_input_tokens: int = 800,
    judge_output_tokens: int = 30,
    judge_price_in_per_1m: float = 0.75,
    judge_price_out_per_1m: float = 3.75,
    validation_fraction: float = 0.10,
) -> pd.DataFrame:
    """Per-model cost ladder from a predictions file's logged usage.

    Model spend = per-run cost × (repeats + cf_arms); judge spend = rows ×
    repeats × per-call price × (1 + validation fraction, for the double-graded
    sample). Missing reconstructed costs fall back to PRICE_OVERRIDES_PER_1M
    on logged tokens; models with no usable cost are flagged, not priced.
    """
    usage = usage_summary_by_model(predictions)
    if models:
        usage = usage[usage["model"].isin(models)]
    households = int(predictions["scenario_id"].nunique()) or 1
    rows_per_model = predictions.groupby("model").size()
    judge_per_call = (
        judge_input_tokens * judge_price_in_per_1m
        + judge_output_tokens * judge_price_out_per_1m
    ) / 1e6
    rows = []
    for _, row in usage.iterrows():
        model = str(row["model"])
        cost = row.get("total_cost_usd")
        basis = "logged"
        if cost is None or pd.isna(cost) or float(cost) == 0.0:
            override = PRICE_OVERRIDES_PER_1M.get(model)
            prompt = row.get("prompt_tokens")
            completion = row.get("completion_tokens")
            if override and prompt is not None and not pd.isna(prompt):
                cost = (
                    float(prompt) * override["input"] / 1e6
                    + float(completion or 0.0) * override["output"] / 1e6
                )
                basis = "override_prices"
            else:
                cost = float("nan")
                basis = "unpriced"
        n_rows = int(rows_per_model.get(model, 0))
        judge_calls = n_rows * repeats * (1.0 + validation_fraction)
        rows.append(
            {
                "model": model,
                "cost_basis": basis,
                "cost_per_run_usd": float(cost) if cost == cost else float("nan"),
                "cost_per_household_usd": (
                    float(cost) / households if cost == cost else float("nan")
                ),
                "arms": repeats + cf_arms,
                "model_spend_usd": (
                    float(cost) * (repeats + cf_arms) if cost == cost else float("nan")
                ),
                "rows_per_run": n_rows,
                "judge_calls": int(round(judge_calls)),
                "judge_spend_usd": judge_calls * judge_per_call,
            }
        )
    plan = pd.DataFrame(rows)
    if plan.empty:
        return plan
    total = {
        "model": "__total__",
        "cost_basis": "",
        "cost_per_run_usd": plan["cost_per_run_usd"].sum(skipna=True),
        "cost_per_household_usd": float("nan"),
        "arms": repeats + cf_arms,
        "model_spend_usd": plan["model_spend_usd"].sum(skipna=True),
        "rows_per_run": int(plan["rows_per_run"].sum()),
        "judge_calls": int(plan["judge_calls"].sum()),
        "judge_spend_usd": plan["judge_spend_usd"].sum(),
    }
    return pd.concat([plan, pd.DataFrame([total])], ignore_index=True)
