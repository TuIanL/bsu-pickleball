import pytest

from app.services.analysis_errors import JobCanceledError, StageTimeoutError, WorkerLeaseLostError
from app.utils.exception_policy import swallow


def test_swallow_records_reason_and_returns_fallback_for_expected_nonfatal_failure():
    @swallow(why="Optional diagnostic source may not be readable.", default=[])
    def read_optional_source():
        raise OSError("device unavailable")

    assert read_optional_source() == []
    assert read_optional_source.__swallow_why__ == "Optional diagnostic source may not be readable."


def test_swallow_requires_an_explicit_nonempty_reason():
    with pytest.raises(ValueError, match="non-empty reason"):
        swallow(why="  ")


@pytest.mark.parametrize("signal", [JobCanceledError, StageTimeoutError, WorkerLeaseLostError])
def test_swallow_never_suppresses_worker_control_signals(signal):
    @swallow(why="Optional diagnostics may fail")
    def probe():
        raise signal("control signal")

    with pytest.raises(signal, match="control signal"):
        probe()
