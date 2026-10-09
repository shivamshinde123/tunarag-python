from decimal import Decimal

import pytest
from live.billing import settled_cost


def ledger():
    return {
        "requests": 1,
        "responses": [{"status": 200, "usage": {"cost": 0.2}}],
        "usage_before_campaign_usd": 0.1,
        "approved_total_usd": 5,
    }


def test_settlement_requires_receipts_and_matches_original_total():
    assert settled_cost(ledger(), 0.3) == Decimal("0.3")
    with pytest.raises(ValueError, match="reconciled"):
        settled_cost(ledger(), 0.4)
    incomplete = ledger()
    incomplete["requests"] = 2
    with pytest.raises(ValueError, match="Unsettled"):
        settled_cost(incomplete, 0.3)


@pytest.mark.parametrize("cost", [None, -1, "NaN", "Infinity", "unknown"])
def test_invalid_costs_cannot_release_reservations(cost):
    state = ledger()
    state["responses"][0]["usage"]["cost"] = cost
    with pytest.raises(ValueError):
        settled_cost(state, 0.3)


def test_failure_or_exceeded_authorization_cannot_reconcile():
    state = ledger()
    state["responses"][0]["status"] = 503
    with pytest.raises(ValueError, match="failure"):
        settled_cost(state, 0.3)
    state = ledger()
    state["approved_total_usd"] = 0.25
    with pytest.raises(ValueError, match="authorization"):
        settled_cost(state, 0.3)
