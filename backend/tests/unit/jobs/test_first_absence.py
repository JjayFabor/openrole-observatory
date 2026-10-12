import pytest

from app.jobs.first_absence import find_missing_external_job_ids


@pytest.mark.parametrize(
    "observed,present,missing",
    [
        ({"1001", "1002", "1003"}, {"1001", "1003"}, {"1002"}),
        ({"1001", "1002"}, set(), {"1001", "1002"}),
        ({"1001", "1002"}, {"1001", "1002"}, set()),
        ({"1001"}, {"1001", "unpersisted"}, set()),
        (set(), {"1001"}, set()),
    ],
)
def test_missing_external_job_ids(
    observed: set[str], present: set[str], missing: set[str]
) -> None:
    assert find_missing_external_job_ids(
        frozenset(observed), frozenset(present)
    ) == frozenset(missing)
