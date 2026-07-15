from pricing import UNKNOWN_COST, CallMeta, combine, compute_cost, format_cost


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


def test_callmeta_one_known_call():
    meta = CallMeta()
    meta.add_call(cost_usd=0.0123, raw='{"ok":true}')
    assert meta.billable_calls == 1
    assert meta.unknown_calls == 0
    assert meta.total_usd() == 0.0123
    assert meta.cost_cell() == "0.012300"
    assert meta.raws == ['{"ok":true}']


def test_callmeta_unknown_mixed_with_known():
    meta = CallMeta()
    meta.add_call(cost_usd=0.01, raw="a")
    meta.add_call(cost_usd=None, raw="b")
    assert meta.billable_calls == 2
    assert meta.unknown_calls == 1
    assert meta.total_usd() is None
    assert meta.cost_cell() == UNKNOWN_COST


def test_combine_sums_fields():
    a = CallMeta()
    a.add_call(cost_usd=0.01, raw="a")
    b = CallMeta()
    b.add_call(cost_usd=0.02, raw="b")
    b.add_call(cost_usd=None, raw="c")
    c = combine([a, b])
    assert c.known_usd == 0.03
    assert c.billable_calls == 3
    assert c.unknown_calls == 1
    assert c.raws == ["a", "b", "c"]
    assert c.total_usd() is None
