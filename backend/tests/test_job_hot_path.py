from pathlib import Path

import pytest

from app.services.job_orchestration import JobStore
from test_analysis_worker_liveness import make_job, make_storage


@pytest.mark.parametrize("count", [1, 100, 1000])
def test_query_operation_counts_do_not_grow_with_history(tmp_path, monkeypatch, count):
    storage = make_storage(tmp_path)
    store = JobStore(storage)
    job = make_job(store)
    payload = job.model_dump(mode="json")
    store.control_plane.import_legacy(({**payload, "id": f"history-{i}"} for i in range(count)), force=True)
    queries = []
    connect = store.control_plane._connect

    def traced():
        connection = connect()
        connection.set_trace_callback(queries.append)
        return connection

    def forbidden(*args, **kwargs):
        raise AssertionError("hot path accessed legacy files")

    monkeypatch.setattr(store.control_plane, "_connect", traced)
    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(storage, "read_json", forbidden)
    monkeypatch.setattr(storage, "write_json_atomic", forbidden)
    assert store.get(job.id).id == job.id
    assert len(store.list()) == count + 1
    assert store.control_plane.get_cancel_state(job.id)[0] == "queued"
    assert len(queries) == 3
    assert all(query.startswith("SELECT") for query in queries)
