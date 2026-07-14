from pricing import UNKNOWN_COST, compute_cost, format_cost


def test_known_price_usd():
    # 1M input + 1M output at gpt-4.1 rates → 2 + 8 = 10
    assert compute_cost("gpt-4.1", 1_000_000, 1_000_000) == 10.0


def test_missing_price_is_none_not_zero():
    assert compute_cost("no-such-model", 100, 100) is None
    assert format_cost(None) == UNKNOWN_COST
    assert format_cost(None) != "0"
    assert format_cost(None) != "0.000000"


def test_format_known_cost():
    assert format_cost(0.012345678) == "0.012346"
