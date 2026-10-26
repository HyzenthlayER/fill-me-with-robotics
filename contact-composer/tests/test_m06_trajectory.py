import numpy as np

from contact_composer.project import standing_project
from contact_composer.trajectory import generate, validate_trajectory


def test_standing_dense_generation_and_independent_force_check():
    p = standing_project(40)
    result = generate(p)
    assert result.solve_status == "success", result.summary()
    assert result.check_status == "passed", result.summary()
    assert len(result.time_s) == 201
    np.testing.assert_allclose(result.q[0], p.initial_state.q, atol=1e-12)
    result.contact_force_world[100, 0, 1] += 10
    issues = validate_trajectory(p, result)
    assert any(i.code == "STATIC_BALANCE" and i.time_interval_s[0] == 1 for i in issues)


def test_middle_sample_contact_error_is_detected():
    p = standing_project(40)
    result = generate(p)
    result.q[100, 3] += 0.05
    issues = validate_trajectory(p, result)
    assert any(i.code == "CONTACT_POSITION" for i in issues)


def test_cancellation_has_no_passed_label():
    result = generate(standing_project(40), cancel=lambda: True)
    assert result.solve_status == "cancelled"
    assert result.check_status == "incomplete"
    assert len(result.time_s) == 0


def test_nonfinite_missing_samples_and_forged_derivatives():
    p = standing_project(40)
    result = generate(p)
    result.dq[50, 3] = 1
    assert any(i.code == "INVALID_DERIVATIVE" for i in validate_trajectory(p, result))
    result.dq[50, 3] = np.nan
    assert validate_trajectory(p, result)[0].code == "INVALID_ARRAY"
    result.dq[50, 3] = 0
    result.time_s[-1] -= 0.1
    assert validate_trajectory(p, result)[0].code == "INCOMPLETE"
