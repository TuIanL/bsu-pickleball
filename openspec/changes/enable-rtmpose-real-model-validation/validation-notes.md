## Environment Preflight

Commands run:

```bash
python3 backend/scripts/validate_rtmpose.py --check-only
backend/.venv/bin/python backend/scripts/validate_rtmpose.py --check-only
backend/.venv/bin/python backend/scripts/validate_rtmpose.py
```

Observed status:

- System `python3` is 3.9.6, below the backend's Python 3.10+ requirement.
- Existing backend `.venv` is Python 3.11.14.
- Existing backend `.venv` has `torch`, `numpy`, and `cv2`.
- Existing backend `.venv` is still missing `mmpose`, `mmcv`, and `mmengine`.
- No RTMPose config/checkpoint paths are configured yet.
- Full validation currently exits with clear missing-runtime and missing-asset
  diagnostics instead of a stack trace.

True-model single-frame and short-video verification remain blocked until the
MMPose/MMCV/MMEngine runtime and RTMPose Body8-Halpe26 assets are installed.

## Regression Checks

Commands run:

```bash
cd backend
../backend/.venv/bin/python -m pytest tests/test_rtmpose26_adapter.py tests/test_api_smoke.py -q
../backend/.venv/bin/python -m pytest -q
cd ..
npm run build
```

Observed status:

- Focused RTMPose adapter/API tests: 22 passed.
- Full backend tests: 43 passed.
- Frontend production build completed successfully.
