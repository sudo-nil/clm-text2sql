from eval.run import rows_equal


def test_identical_rows_pass():
    assert rows_equal([{"n": 5}], [{"n": 5}], order_sensitive=False)


def test_order_insensitive_by_default():
    expected = [{"id": 1}, {"id": 2}]
    actual = [{"id": 2}, {"id": 1}]
    assert rows_equal(expected, actual, order_sensitive=False)


def test_order_sensitive_when_flagged():
    expected = [{"id": 1}, {"id": 2}]
    actual = [{"id": 2}, {"id": 1}]
    assert not rows_equal(expected, actual, order_sensitive=True)


def test_extra_columns_in_actual_are_tolerated():
    expected = [{"contract_id": "CT-1"}]
    actual = [{"contract_id": "CT-1", "title": "whatever"}]
    assert rows_equal(expected, actual, order_sensitive=False)


def test_wrong_row_set_fails():
    expected = [{"contract_id": "CT-1"}]
    actual = [{"contract_id": "CT-2"}]
    assert not rows_equal(expected, actual, order_sensitive=False)


def test_both_empty_pass():
    assert rows_equal([], [], order_sensitive=False)


def test_one_sided_empty_fails():
    assert not rows_equal([{"n": 1}], [], order_sensitive=False)
