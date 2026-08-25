"""Tests for reasoning stability (stability spec layer 2).

The LLM judge is mocked everywhere; these tests pin the deterministic
machinery around it: numeric-claim extraction, pair construction, label
agreement metrics with their composition companions, the validation
statistics, and the extraction runner's dedup/retry/cache behavior.
"""

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from policybench.annotation_taxonomy import FAILURE_SUBTYPE_VALUES
from policybench.reasoning_stability import (
    JUDGE_PROMPT_VERSION,
    MECHANISM_LABELS,
    SUPER_DOMAINS,
    build_judge_prompt,
    cohen_kappa,
    dominant_set_share,
    evaluate_against_gold,
    explanation_pair_frame,
    extract_numeric_claims,
    gwet_ac1,
    judge_cache_key,
    krippendorff_alpha_jaccard,
    normalize_explanation_text,
    parse_judge_labels,
    reasoning_stability_by_model,
    reference_alignment_by_model,
    run_label_extraction,
    wilson_ci,
)


class TestLabels:
    def test_label_set_is_taxonomy_minus_missing_output(self):
        assert set(MECHANISM_LABELS) == set(FAILURE_SUBTYPE_VALUES) - {"missing_output"}
        assert len(MECHANISM_LABELS) == 12

    def test_super_domains_partition_the_labels(self):
        covered = [label for labels in SUPER_DOMAINS.values() for label in labels]
        assert sorted(covered) == sorted(MECHANISM_LABELS)
        assert len(SUPER_DOMAINS) == 5


class TestNumericClaims:
    def test_extracts_dollars_and_percents_with_rounding(self):
        claims = extract_numeric_claims(
            "The 6.2% rate applied up to the $176,100 wage base gave $186.00, "
            "plus 1.45% Medicare ($43.50)."
        )
        assert ("pct", 6.2) in claims
        assert ("pct", 1.5) in claims  # 1.45 rounds to 0.1pp
        assert ("usd", 176100) in claims
        assert ("usd", 186) in claims
        assert ("usd", 44) in claims  # 43.50 -> 44 to the dollar

    def test_excludes_the_restated_prediction(self):
        text = "SNAP comes to $288 after the $177 standard deduction."
        assert ("usd", 288) not in extract_numeric_claims(text, exclude_value=287.68)
        assert ("usd", 177) in extract_numeric_claims(text, exclude_value=287.68)

    def test_empty_text(self):
        assert extract_numeric_claims("") == frozenset()
        assert extract_numeric_claims(None) == frozenset()


class TestNormalizationAndPrompt:
    def test_normalization_collapses_case_and_whitespace(self):
        assert normalize_explanation_text("  Two  spaces\nand CASE ") == (
            normalize_explanation_text("two spaces and case")
        )

    def test_prompt_carries_labels_and_version_but_not_comparison(self):
        prompt = build_judge_prompt("Payroll tax is 7.65% of wages.", "payroll_tax")
        for label in MECHANISM_LABELS:
            assert label in prompt
        assert JUDGE_PROMPT_VERSION in prompt
        assert "payroll_tax" in prompt
        # The judge labels one explanation; it never sees a pair or a score.
        assert "compare" not in prompt.lower()

    def test_cache_key_depends_on_text_model_and_pass(self):
        base = judge_cache_key("judge-a", "snap", "Text one.", grade_pass=0)
        assert base == judge_cache_key("judge-a", "snap", "text  ONE.", grade_pass=0)
        assert base != judge_cache_key("judge-b", "snap", "Text one.", grade_pass=0)
        assert base != judge_cache_key("judge-a", "snap", "Text one.", grade_pass=1)
        assert base != judge_cache_key("judge-a", "ssi", "Text one.", grade_pass=0)


class TestParseJudgeLabels:
    def test_parses_json_object(self):
        assert parse_judge_labels(
            '{"labels": ["payroll_tax_base", "thresholds_rates"]}'
        ) == [
            "payroll_tax_base",
            "thresholds_rates",
        ]

    def test_tolerates_fenced_json_and_dedups(self):
        content = '```json\n{"labels": ["other", "other"]}\n```'
        assert parse_judge_labels(content) == ["other"]

    def test_rejects_unknown_labels_and_missing_key(self):
        with pytest.raises(ValueError):
            parse_judge_labels('{"labels": ["not_a_label"]}')
        with pytest.raises(ValueError):
            parse_judge_labels('{"mechanisms": ["other"]}')
        with pytest.raises(ValueError):
            parse_judge_labels("no json here")


def _judge_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class TestExtractionRunner:
    def test_dedups_identical_texts_and_caches_to_disk(self, tmp_path):
        items = [
            {
                "variable": "snap",
                "country": "us",
                "year": 2026,
                "text": "Income exceeds 130% FPL.",
            },
            {
                "variable": "snap",
                "country": "us",
                "year": 2026,
                "text": "income exceeds 130% fpl.",
            },
            {
                "variable": "ssi",
                "country": "us",
                "year": 2026,
                "text": "Neither adult is aged or disabled.",
            },
        ]
        cache = tmp_path / "labels.jsonl"
        acompletion = AsyncMock(
            side_effect=[
                _judge_response(
                    '{"labels": ["categorical_eligibility", "thresholds_rates"]}'
                ),
                _judge_response(
                    '{"labels": ["categorical_eligibility", "age_disability"]}'
                ),
            ]
        )
        with patch("policybench.reasoning_stability.litellm.acompletion", acompletion):
            results = run_label_extraction(items, judge_model="judge", cache_path=cache)
        # Two unique normalized texts -> two calls, three keyed results.
        assert acompletion.call_count == 2
        assert len(results) == 2
        snap_key = judge_cache_key("judge", "snap", items[0]["text"], 0)
        assert results[snap_key]["labels"] == [
            "categorical_eligibility",
            "thresholds_rates",
        ]
        # Second invocation is served entirely from the cache file.
        acompletion.reset_mock()
        with patch("policybench.reasoning_stability.litellm.acompletion", acompletion):
            again = run_label_extraction(items, judge_model="judge", cache_path=cache)
        assert acompletion.call_count == 0
        assert again == results
        assert len(cache.read_text().strip().splitlines()) == 2

    def test_retries_once_then_records_error(self, tmp_path):
        items = [{"variable": "snap", "country": "us", "year": 2026, "text": "x"}]
        acompletion = AsyncMock(
            side_effect=[_judge_response("garbage"), _judge_response("still garbage")]
        )
        with patch("policybench.reasoning_stability.litellm.acompletion", acompletion):
            results = run_label_extraction(
                items, judge_model="judge", cache_path=tmp_path / "c.jsonl"
            )
        assert acompletion.call_count == 2
        (result,) = results.values()
        assert result["labels"] is None
        assert "invalid" in result["error"].lower()

    def test_requests_never_use_litellm_cache_and_pass_temperature_zero(self, tmp_path):
        items = [{"variable": "snap", "country": "us", "year": 2026, "text": "x"}]
        acompletion = AsyncMock(return_value=_judge_response('{"labels": ["other"]}'))
        with patch("policybench.reasoning_stability.litellm.acompletion", acompletion):
            run_label_extraction(
                items, judge_model="judge", cache_path=tmp_path / "c.jsonl"
            )
        kwargs = acompletion.call_args.kwargs
        assert kwargs["caching"] is False
        assert kwargs["temperature"] == 0
        assert kwargs["model"] == "judge"

    def test_grade_pass_forces_independent_calls(self, tmp_path):
        items = [{"variable": "snap", "country": "us", "year": 2026, "text": "x"}]
        acompletion = AsyncMock(return_value=_judge_response('{"labels": ["other"]}'))
        with patch("policybench.reasoning_stability.litellm.acompletion", acompletion):
            run_label_extraction(
                items, judge_model="judge", cache_path=tmp_path / "c.jsonl"
            )
            run_label_extraction(
                items,
                judge_model="judge",
                cache_path=tmp_path / "c.jsonl",
                grade_pass=1,
            )
        assert acompletion.call_count == 2


def _ground_truth():
    return pd.DataFrame(
        {
            "scenario_id": ["s1", "s1", "s2", "s2"],
            "variable": ["snap", "payroll_tax", "snap", "payroll_tax"],
            "value": [100.0, 500.0, 0.0, 700.0],
        }
    )


def _repeated_predictions():
    """Two runs, one model.

    s1/snap: stable + exact, explanations differ (mechanism A vs B).
    s1/payroll: stable + exact, verbatim-identical explanations.
    s2/snap: stable but wrong (both 50 vs ref 0), explanations differ.
    s2/payroll: answer flips (700 vs 900) -> not a stable pair.
    """
    rows = []
    for run_id, preds, texts in [
        (
            "run_000",
            [100.0, 500.0, 50.0, 700.0],
            ["Net income test applied.", "7.65% of wages.", "Asset test failed.", "A"],
        ),
        (
            "run_001",
            [100.0, 500.0, 50.0, 900.0],
            ["Gross income under 130% FPL.", "7.65%  of wages.", "Gross test.", "B"],
        ),
    ]:
        for (sid, var), pred, text in zip(
            [
                ("s1", "snap"),
                ("s1", "payroll_tax"),
                ("s2", "snap"),
                ("s2", "payroll_tax"),
            ],
            preds,
            texts,
            strict=True,
        ):
            rows.append(
                {
                    "run_id": run_id,
                    "model": "m",
                    "scenario_id": sid,
                    "variable": var,
                    "prediction": pred,
                    "explanation": text,
                }
            )
    return pd.DataFrame(rows)


class TestExplanationPairFrame:
    def test_pairs_carry_strata_and_verbatim_flag(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        by_row = pairs.set_index(["scenario_id", "variable"])
        assert len(pairs) == 4
        s1_snap = by_row.loc[("s1", "snap")]
        assert bool(s1_snap["stable"]) and bool(s1_snap["stable_exact"])
        assert not bool(s1_snap["verbatim_identical"])
        s1_pay = by_row.loc[("s1", "payroll_tax")]
        assert bool(s1_pay["stable_exact"]) and bool(s1_pay["verbatim_identical"])
        s2_snap = by_row.loc[("s2", "snap")]
        assert bool(s2_snap["stable"]) and not bool(s2_snap["stable_exact"])
        s2_pay = by_row.loc[("s2", "payroll_tax")]
        assert not bool(s2_pay["stable"])
        assert "text_key_a" in pairs.columns and "output_group" in pairs.columns


def _labels_for(pairs, mapping):
    """Build labels_by_text_key from explanation text -> label set."""
    out = {}
    for _, row in pairs.iterrows():
        for side in ("a", "b"):
            text = row[f"explanation_{side}"]
            if text in mapping:
                out[row[f"text_key_{side}"]] = frozenset(mapping[text])
    return out


class TestReasoningMetrics:
    def test_headline_and_companions(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        labels = _labels_for(
            pairs,
            {
                "Net income test applied.": {"thresholds_rates"},
                "Gross income under 130% FPL.": {
                    "categorical_eligibility",
                    "thresholds_rates",
                },
                "Asset test failed.": {"asset_resource"},
                "Gross test.": {"thresholds_rates"},
            },
        )
        result = reasoning_stability_by_model(pairs, labels, min_stable_exact_pairs=1)
        row = result["summary"].set_index("model").loc["m"]
        assert row["n_pairs_total"] == 4
        assert row["n_stable_pairs"] == 3
        assert row["n_stable_exact_pairs"] == 2
        # Stable-exact: s1/snap disagrees, s1/payroll verbatim-identical agrees.
        assert row["mechanism_agreement_rate_stable_exact"] == pytest.approx(0.5)
        assert row["right_answer_unstable_reasoning_rate"] == pytest.approx(0.5)
        # Restricted to non-identical texts: only s1/snap remains -> 1.0.
        assert row[
            "right_answer_unstable_reasoning_rate_nonidentical"
        ] == pytest.approx(1.0)
        assert row["short_circuit_share_stable"] == pytest.approx(1 / 3)
        # Joint rate over ALL pairs: one stable∧exact∧divergent pair of 4.
        assert row["joint_unstable_reasoning_rate_all_pairs"] == pytest.approx(0.25)
        # Stable stratum (3 pairs): s1/snap differ, s1/payroll same, s2/snap differ.
        assert row["mechanism_agreement_rate_stable"] == pytest.approx(1 / 3)
        assert row["mechanism_jaccard_mean_stable_exact"] == pytest.approx(
            (0.5 + 1.0) / 2
        )
        assert bool(row["headline_suppressed"]) is False

    def test_suppression_rule(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        labels = _labels_for(pairs, {})
        result = reasoning_stability_by_model(pairs, labels, min_stable_exact_pairs=200)
        row = result["summary"].set_index("model").loc["m"]
        assert bool(row["headline_suppressed"]) is True

    def test_judge_errors_excluded_and_counted(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        # No labels at all: every non-identical stable pair is unjudged.
        result = reasoning_stability_by_model(pairs, {}, min_stable_exact_pairs=1)
        row = result["summary"].set_index("model").loc["m"]
        assert row["n_unjudged_stable_pairs"] == 2
        # Only the verbatim pair is gradeable -> agreement 1.0 on n=1.
        assert row["mechanism_agreement_rate_stable_exact"] == pytest.approx(1.0)

    def test_attenuation_adjustment(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        labels = _labels_for(
            pairs,
            {
                "Net income test applied.": {"thresholds_rates"},
                "Gross income under 130% FPL.": {"categorical_eligibility"},
            },
        )
        result = reasoning_stability_by_model(
            pairs, labels, min_stable_exact_pairs=1, pair_noise_floor=0.2
        )
        row = result["summary"].set_index("model").loc["m"]
        observed = row["right_answer_unstable_reasoning_rate"]
        assert row["right_answer_unstable_reasoning_rate_adjusted"] == pytest.approx(
            max(0.0, (observed - 0.2) / 0.8)
        )

    def test_numeric_claim_channel(self):
        preds = _repeated_predictions()
        preds.loc[
            (preds["scenario_id"] == "s1") & (preds["variable"] == "snap"),
            "explanation",
        ] = ["Deduction of $177 and 30% rate.", "Deduction of $177 and 24% rate."]
        pairs = explanation_pair_frame(preds, _ground_truth())
        result = reasoning_stability_by_model(pairs, {}, min_stable_exact_pairs=1)
        row = result["summary"].set_index("model").loc["m"]
        # Claims {177, 30%} vs {177, 24%}: Jaccard 1/3; shared $177 -> not disjoint.
        assert row["numeric_claim_jaccard_mean_stable_exact"] == pytest.approx(
            (1 / 3 + 1.0) / 2  # the verbatim payroll pair contributes Jaccard 1
        )

    def test_composition_table_and_standardized_rate(self):
        pairs = explanation_pair_frame(_repeated_predictions(), _ground_truth())
        labels = _labels_for(
            pairs,
            {
                "Net income test applied.": {"thresholds_rates"},
                "Gross income under 130% FPL.": {"categorical_eligibility"},
            },
        )
        result = reasoning_stability_by_model(pairs, labels, min_stable_exact_pairs=1)
        composition = result["composition"]
        assert set(composition["output_group"]) == {"snap", "payroll_tax"}
        row = result["summary"].set_index("model").loc["m"]
        # Equal composition (one pair per group): standardized equals the mean
        # of per-group rates (1.0 for snap, 0.0 for payroll).
        assert row["standardized_unstable_reasoning_rate"] == pytest.approx(0.5)


class TestReferenceAlignment:
    def test_alignment_among_exact_rows(self):
        preds = _repeated_predictions()
        pairs = explanation_pair_frame(preds, _ground_truth())
        labels = _labels_for(
            pairs,
            {
                "Net income test applied.": {"thresholds_rates"},
                "Gross income under 130% FPL.": {"categorical_eligibility"},
                "7.65% of wages.": {"payroll_tax_base"},
                "7.65%  of wages.": {"payroll_tax_base"},
            },
        )
        reference_labels = {
            ("s1", "snap"): frozenset({"categorical_eligibility"}),
            ("s1", "payroll_tax"): frozenset({"payroll_tax_base"}),
            ("s2", "snap"): frozenset({"thresholds_rates"}),
            ("s2", "payroll_tax"): frozenset({"payroll_tax_base"}),
        }
        table = reference_alignment_by_model(
            preds, _ground_truth(), labels, reference_labels
        )
        row = table.set_index("model").loc["m"]
        # Exact-correct run-explanations: s1/snap x2, s1/payroll x2, s2/payroll run_000.
        # Labeled among them: s1/snap (1 of 2 aligned), s1/payroll (2 aligned).
        assert row["n_exact_labeled"] == 4
        assert row["reference_alignment_rate"] == pytest.approx(3 / 4)


class TestAgreementStatistics:
    def test_gwet_ac1_and_kappa_known_values(self):
        # 40 items, one disagreement each way at 97.5% prevalence: raw
        # agreement 0.95, kappa goes negative (the prevalence paradox), AC1 holds.
        a = [True] * 39 + [False]
        b = [True] * 38 + [False] + [True]
        kappa = cohen_kappa(a, b)
        ac1 = gwet_ac1(a, b)
        assert kappa < 0.0
        assert ac1 > 0.9
        assert gwet_ac1([True, False], [True, False]) == pytest.approx(1.0)

    def test_kappa_perfect_and_chance(self):
        assert cohen_kappa(
            [True, False, True, False], [True, False, True, False]
        ) == pytest.approx(1.0)
        assert cohen_kappa(
            [True, True, False, False], [True, False, True, False]
        ) == pytest.approx(0.0)

    def test_krippendorff_alpha_jaccard(self):
        perfect = [
            (frozenset({"a"}), frozenset({"a"})),
            (frozenset({"b"}), frozenset({"b"})),
            (frozenset({"a", "c"}), frozenset({"a", "c"})),
        ]
        assert krippendorff_alpha_jaccard(perfect) == pytest.approx(1.0)
        noisy = [
            (frozenset({"a"}), frozenset({"b"})),
            (frozenset({"b"}), frozenset({"a"})),
        ]
        assert krippendorff_alpha_jaccard(noisy) < 0.0

    def test_dominant_set_share(self):
        sets = [frozenset({"a"}), frozenset({"a"}), frozenset({"b"})]
        assert dominant_set_share(sets) == pytest.approx(2 / 3)
        assert math.isnan(dominant_set_share([]))

    def test_wilson_ci(self):
        low, high = wilson_ci(90, 100)
        assert 0.82 < low < 0.90 < high < 0.95
        low, high = wilson_ci(0, 0)
        assert math.isnan(low) and math.isnan(high)


class TestGoldEvaluation:
    def test_exact_set_accuracy_and_per_label(self):
        gold = pd.DataFrame(
            {
                "variable": ["snap", "ssi"],
                "explanation": ["Income exceeds 130% FPL.", "Not aged or disabled."],
                "labels": [
                    "categorical_eligibility|thresholds_rates",
                    "age_disability",
                ],
            }
        )
        labels_by_key = {
            judge_cache_key("judge", "snap", "Income exceeds 130% FPL.", 0): frozenset(
                {"categorical_eligibility", "thresholds_rates"}
            ),
            judge_cache_key("judge", "ssi", "Not aged or disabled.", 0): frozenset(
                {"age_disability", "other"}
            ),
        }
        summary = evaluate_against_gold(gold, labels_by_key, judge_model="judge")
        assert summary["n_gold"] == 2
        assert summary["n_graded"] == 2
        assert summary["exact_set_accuracy"] == pytest.approx(0.5)
        assert summary["exact_set_accuracy_ci_low"] < 0.5
        per_label = summary["per_label"].set_index("label")
        assert per_label.loc["other", "judge_positives"] == 1
        assert per_label.loc["other", "gold_positives"] == 0
        assert per_label.loc["age_disability", "agreement"] == pytest.approx(1.0)
