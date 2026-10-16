from scripts.check_exception_policy import policy_errors


def test_new_silent_broad_handler_is_rejected():
    source = "def probe():\n    try:\n        work()\n    except Exception:\n        pass\n"
    assert len(policy_errors(source, {4, 5}, "probe.py")) == 1
    assert policy_errors(source, {1}, "probe.py") == []


def test_narrow_race_and_observable_failure_are_allowed():
    narrow = "try:\n    remove()\nexcept FileNotFoundError:\n    pass\n"
    visible = "try:\n    work()\nexcept Exception:\n    logger.exception('failed')\n"
    assert policy_errors(narrow, {3, 4}, "probe.py") == []
    assert policy_errors(visible, {3, 4}, "probe.py") == []


def test_swallow_requires_a_literal_nonempty_reason():
    valid = "@swallow(why='Optional diagnostic only')\ndef probe():\n    return work()\n"
    assert policy_errors(valid, {2, 3}, "probe.py") == []
    assert len(policy_errors(valid.replace("'Optional diagnostic only'", "''"), {1}, "probe.py")) == 1
    assert len(policy_errors(valid.replace("'Optional diagnostic only'", "runtime_reason"), {2}, "probe.py")) == 1
