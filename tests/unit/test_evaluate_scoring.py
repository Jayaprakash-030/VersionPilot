from eval.evaluate_scoring import count_misleading_verified_low_results


def test_failure_scenarios_do_not_publish_verified_low_results():
    assert count_misleading_verified_low_results() == 0
