# Delivery verification — 2026-09-08

## Isolated installs

All backend commands below used CPython 3.11.15 on macOS arm64, in newly created
virtual environments under `/tmp` with no project-local virtual environment or
model assets. The lock was regenerated with:

```sh
uv pip compile backend/pyproject.toml --extra dev --python-version 3.11 \
  --generate-hashes --no-annotate --output-file backend/requirements-py311.lock
```

Both supported installation paths succeeded:

```sh
uv pip install --python <venv>/bin/python --require-hashes -r backend/requirements.txt
uv pip install --python <venv>/bin/python --constraint backend/requirements-py311.lock './backend[dev]'
```

The former imported `fastapi`, `sqlalchemy`, and `scipy`; the latter imported
the packaged `app` module. Optional vision, pose, and training extras were not
installed by either command.

## Quality gates

The final base-suite run was:

```sh
/tmp/pre-pickleball-reliability-base/bin/python -m pytest -q
```

It completed with **1500 passed, 2 skipped**. The skips are explicitly
optional-model cases, not ignored base failures. The only warnings are existing
Pydantic serializer warnings in analysis fixture data and deprecation warnings.

In a fresh Node 22.23.2 directory, `npm ci`, `npm run build`,
`npm test -- --maxWorkers=2`, and `npm run lint` completed. The frontend result
was **670 passed**; lint had **0 errors and 41 pre-existing warnings**. The
landing static JavaScript gzip total was **109,732 bytes** (limit: 358,400),
and CSS was reported separately as 19,322 bytes. `openspec validate
harden-project-reliability-and-delivery --strict` passed and `git diff --check`
reported no whitespace errors.

## Functional evidence

| Area | Evidence |
| --- | --- |
| Candidate decisions | `test_candidate_reliability_api.py` uses independent SQLite connections to accept, correct, reject, replay an identical request, reject altered payloads, roll back an injected commit failure, and arbitrate same-revision writers. It also verifies malformed JSON exports cannot hide committed decisions. |
| Candidate migration | The migration tests exercise dry-run, verified import, repeat import, broken references as `legacy_unbound`, file hashes, SQLite backup, schema upgrade/repeat/downgrade, and restoration from the original backup. Camera migration is dry-run-first, non-destructive, idempotent, and rejects invalid/mismatched IDs. |
| Video and upload | `test_video_stream_range.py` covers MIME, parser grammar, GET/HEAD, ranges and closed handles. `test_upload_limits.py` covers cumulative unknown-length limits, failed cleanup, metadata cleanup, poster failure, and an event-loop barrier while poster extraction waits. |
| Browser playback | In real Chrome against the local FastAPI server, a generated H.264 160×120 MP4 loaded, played, and sought from 0:00 to 0:02 of 0:04. A deliberately invalid AVI made an HTTP range request successfully but the UI visibly showed “视频暂不可用，请稍后重试”, proving the browser-decode fallback is distinct from HTTP success. Test files were moved out of the workspace data directory afterwards. |
| Job hot path | `test_job_hot_path.py` seeds 1, 100, and 1000 historical jobs, forbids JSON file operations, and observes exactly three `SELECT`s for get/list/cancel-state. Existing worker-liveness tests cover cancellation, heartbeat, lease, terminal recovery, and explicit legacy import. |
| Projection diagnostics | `test_projection_delivery.py` verifies all four JSONL/overlay switch combinations, no minimap when JSONL is disabled, and closes both writers after an injected tracking failure. |

## Boundaries not claimed as passed

This verification did not run a trained learned-match-state model, RTMPose,
YOLO, a real dual-camera capture, or a physical camera. Those require trusted
weights and compatible vision/pose dependencies, plus two synchronized camera
feeds and calibration. The base runtime, API/worker status transitions,
candidate-review contract, and browser playback path are verified; model
accuracy, hardware timing, and real dual-camera acceptance remain separate
environment-dependent acceptance work.
