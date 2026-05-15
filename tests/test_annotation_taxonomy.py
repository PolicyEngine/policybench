from policybench.annotation_taxonomy import infer_failure_category


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
