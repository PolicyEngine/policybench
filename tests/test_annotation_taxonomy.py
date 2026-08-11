from policybench.annotation_taxonomy import (
    FAILURE_SOURCE_VALUES,
    infer_failure_category,
    validate_failure_source,
)


def test_missing_parsed_prediction_is_parse_contract_failure() -> None:
    category = infer_failure_category(
        "Missing parsed prediction/explanation; reference benefit is GBP 1,400.66."
    )

    assert category.failure_source == "parse_contract_failure"
    assert category.failure_subtype == "missing_output"


def test_model_omitted_policy_amount_is_not_parse_contract_failure() -> None:
    category = infer_failure_category(
        "Model omitted CGT despite PE chargeable gains above the annual exemption; "
        "underestimate is GBP 70.63."
    )

    assert category.failure_source == "llm_error"
    assert category.failure_subtype == "thresholds_rates"


def test_budget_exhaustion_is_a_valid_distinct_failure_source() -> None:
    source = "budget_exhausted_at_ceiling"

    assert source in FAILURE_SOURCE_VALUES
    assert validate_failure_source(source) == source
