## Why

The backend already reserves a CourtVision Calibration Engine boundary, but the current MVP only covers a thin geometry and homography skeleton. Fixed-camera pickleball analysis needs a complete manual calibration path so image pixels can be mapped into canonical court coordinates and visual overlays can verify calibration quality before downstream tracking and metrics consume it.

## What Changes

- Expand the CourtVision Calibration Engine with a standard 20 ft by 44 ft pickleball court geometry model, canonical keypoints, court lines, kitchen regions, and service-zone polygons.
- Replace the current homography implementation with OpenCV RANSAC-based computation and add validated single-point and batch coordinate transforms in both directions.
- Add a manual keypoint calibration flow that accepts clicked image points, automatically matches standard court keypoints for the MVP four-corner workflow, returns homography and inverse homography matrices, and reports calibration quality.
- Add overlay rendering that projects standard court geometry back onto a video frame, including court boundary, net, kitchen lines, center lines, and translucent region fills.
- Add calibration API endpoints for manual calibration creation, calibration retrieval, and overlay preview generation while preserving compatibility with existing backend calibration consumers where practical.
- Add focused tests for court geometry constants, canonical keypoints, homography transforms, batch transforms, and invalid input handling.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pickleball-algorithm-backend-mvp`: Strengthen the CourtVision Calibration Engine requirements from a basic MVP skeleton into a usable manual calibration, homography, inverse-projection, geometry, overlay, and preview API contract.

## Impact

- Affected backend modules:
  - `backend/app/vision/courtvision_calibration_engine/court_geometry.py`
  - `backend/app/vision/courtvision_calibration_engine/homography.py`
  - `backend/app/vision/courtvision_calibration_engine/manual_keypoint_calibrator.py`
  - `backend/app/vision/courtvision_calibration_engine/court_overlay.py`
  - `backend/app/schemas/calibration.py`
  - `backend/app/services/calibration_service.py`
  - `backend/app/api/routes_calibration.py`
- Affected tests:
  - `backend/tests/test_court_geometry.py`
  - `backend/tests/test_homography.py`
  - optional API preview smoke coverage if implementation scope permits.
- Dependencies:
  - Uses the existing OpenCV dependency declared by the backend for `cv2.findHomography` and overlay rendering.
- API impact:
  - Adds `/calibration/manual`, `/calibration/{calibration_id}`, and `/calibration/{calibration_id}/preview` style endpoints requested for the CourtVision workflow.
  - Existing `/api/calibrations` routes should remain available unless a later decision explicitly removes them.
