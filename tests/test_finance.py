import copy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finance import compare_proposal, financial_profile, monthly_payment
from schemas import ClientData, Proposal


def test_profile_uses_annual_net_income_and_excludes_duplicate_expenses(sample_data):
    metrics = financial_profile(sample_data)
    assert metrics["income"] == 3000
    assert metrics["debt"] == 90000
    assert metrics["dti"] == 2.5
    assert metrics["debt_service_ratio"] == 21
    assert metrics["disposable"] == 1170
    assert metrics["reserve_months"] == 3.28


def test_zero_income_is_undefined_not_false_approval(sample_data):
    sample_data["income_employment"] = "0"
    metrics = financial_profile(sample_data)
    assert metrics["dti"] is None
    assert metrics["debt_service_ratio"] is None
    assert metrics["disposable"] == -1830


def test_cards_include_unused_limit_in_separate_dti(sample_data):
    sample_data["debts"] = [{"id": "card", "kind": "card", "lender": "", "balance": "1000", "limit": "5000", "payment": "50", "rate": "20"}]
    metrics = financial_profile(sample_data)
    assert metrics["debt"] == 1000
    assert metrics["dti"] == 0.03
    assert metrics["dti_with_limits"] == 0.05


def test_annuity_and_zero_interest():
    assert monthly_payment(100000, 4, 30) == Decimal("477.42")
    assert monthly_payment(12000, 0, 10) == Decimal("100.00")
    with pytest.raises(ValueError):
        monthly_payment(1000, -1, 10)


def test_refinance_replaces_only_selected_debts(sample_data, proposal_data):
    proposal_data.update(principal="85000", replace_ids=["debt-1"])
    comparison = compare_proposal(sample_data, proposal_data)
    new_payment = float(monthly_payment(85000, 3.6, 25))
    assert comparison["debt_after"] == 90000
    assert comparison["payments_after"] == round(new_payment + 150, 2)
    assert comparison["monthly_change"] == round(480 - new_payment - 20, 2)
    assert comparison["dsti_estimate"] is None


def test_new_mortgage_keeps_existing_payments(sample_data, proposal_data):
    proposal_data.update(kind="mortgage", principal="100000", replace_ids=[], monthly_costs="0")
    result = compare_proposal(sample_data, proposal_data)
    assert result["debt_after"] == 190000
    assert result["payments_after"] > 630
    assert result["monthly_change"] < 0
    assert result["break_even_months"] is None


def test_unknown_or_underfunded_refinance_is_rejected(sample_data, proposal_data):
    proposal_data["replace_ids"] = ["somebody-elses-debt"]
    with pytest.raises(ValueError):
        compare_proposal(sample_data, proposal_data)
    proposal_data.update(replace_ids=["debt-1"], principal="80000")
    with pytest.raises(ValueError):
        compare_proposal(sample_data, proposal_data)


def test_dsti_requires_separate_assessed_payment_and_positive_base(sample_data, proposal_data):
    proposal_data.update(living_minimum="1000", assessed_payments="800")
    assert compare_proposal(sample_data, proposal_data)["dsti_estimate"] == 40
    proposal_data["living_minimum"] = "3000"
    assert compare_proposal(sample_data, proposal_data)["dsti_estimate"] is None


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "1e100", "12.123"])
def test_invalid_money_rejected(sample_data, value):
    sample_data["expenses"] = value
    with pytest.raises(ValidationError):
        ClientData.model_validate(sample_data)


def test_credit_card_limit_validation(sample_data):
    sample_data["debts"][0].update(kind="card", limit="100")
    with pytest.raises(ValidationError):
        ClientData.model_validate(sample_data)


def test_refinance_requires_explicit_replaced_debt(proposal_data):
    proposal_data["replace_ids"] = []
    with pytest.raises(ValidationError):
        Proposal.model_validate(proposal_data)
