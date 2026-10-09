from decimal import Decimal, InvalidOperation


def settled_cost(ledger, key_usage):
    receipts = ledger["responses"]
    if len(receipts) != ledger["requests"]:
        raise ValueError("Unsettled requests must retain their reservations")
    total = Decimal(str(ledger["usage_before_campaign_usd"]))
    for receipt in receipts:
        if receipt["status"] != 200:
            raise ValueError("Unconfirmed failure charges need manual reconciliation")
        try:
            cost = Decimal(str(receipt["usage"]["cost"]))
        except (KeyError, TypeError, InvalidOperation) as error:
            raise ValueError("A receipt is missing an exact provider cost") from error
        if not cost.is_finite() or cost < 0:
            raise ValueError("Provider cost must be finite and nonnegative")
        total += cost
    observed = Decimal(str(key_usage))
    if not observed.is_finite() or abs(observed - total) > Decimal("0.000001"):
        raise ValueError("Provider key usage has not reconciled with receipts")
    if total > Decimal(str(ledger["approved_total_usd"])):
        raise ValueError("Original cumulative authorization exceeded")
    return total
