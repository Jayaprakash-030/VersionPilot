from arrays import mask_dtype


def test_mask_dtype_uses_builtin_bool():
    assert mask_dtype() is bool
