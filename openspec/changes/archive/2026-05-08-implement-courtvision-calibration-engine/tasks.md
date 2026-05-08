## 1. Geometry Model

- [x] 1.1 Implement `PickleballCourtGeometry` with canonical dimensions, net/kitchen constants, court coordinate-system metadata, and compatibility aliases for existing imports.
- [x] 1.2 Add standard keypoint accessors for `top_left`, `top_right`, `bottom_right`, and `bottom_left` with float coordinates.
- [x] 1.3 Add deterministic line and polygon accessors for outer boundary, net, kitchen boundaries, center service lines, kitchen zones, and left/right service zones.
- [x] 1.4 Preserve existing zone membership helpers used by performance metrics.

## 2. Homography Utilities

- [x] 2.1 Replace homography computation with `cv2.findHomography(..., cv2.RANSAC)` and raise `HomographyError` for invalid or degenerate inputs.
- [x] 2.2 Validate point arrays for minimum count, matching count, finite numeric values, and two-dimensional shape.
- [x] 2.3 Implement `image_to_court(point_or_points, H)` supporting both one point and batches.
- [x] 2.4 Implement `court_to_image(point_or_points, H_inv)` supporting both one point and batches.
- [x] 2.5 Keep `project_point` compatibility for existing player projection code.

## 3. Manual Calibration Flow

- [x] 3.1 Add schemas for named manual calibration requests, calibration quality, court coordinate-system metadata, inverse homography, and preview responses.
- [x] 3.2 Implement manual keypoint calibration that maps named image points to standard court keypoints for the MVP four-corner workflow.
- [x] 3.3 Compute and serialize both homography and inverse homography matrices as nested float lists.
- [x] 3.4 Compute reprojection error and return a quality status for successful calibration.
- [x] 3.5 Store and retrieve the richer calibration result through the existing local calibration storage path.

## 4. Overlay Rendering and Preview

- [x] 4.1 Update overlay rendering to accept a frame, inverse homography, and court geometry.
- [x] 4.2 Draw projected outer boundary, net line, kitchen boundaries, and center service lines on the frame.
- [x] 4.3 Add translucent fills for kitchen and service-zone polygons while preserving the original frame dimensions.
- [x] 4.4 Implement preview generation that accepts an uploaded/input frame or reads the first frame from a stored video when available.
- [x] 4.5 Save generated preview images under output storage and return the preview image path.

## 5. API Integration

- [x] 5.1 Add `POST /calibration/manual` with the requested named-corner JSON request shape and response fields.
- [x] 5.2 Add `GET /calibration/{calibration_id}` returning the saved calibration result.
- [x] 5.3 Add `POST /calibration/{calibration_id}/preview` returning an overlay preview path or a clear error.
- [x] 5.4 Preserve existing `/api/calibrations` endpoints and update them only as needed for compatibility with richer calibration results.
- [x] 5.5 Ensure API errors map calibration and homography validation failures to clear 400-level responses and unknown ids to 404 responses.

## 6. Tests and Verification

- [x] 6.1 Expand `backend/tests/test_court_geometry.py` to cover dimensions, net y=22, kitchen boundaries y=15/y=29, keypoint count, and keypoint coordinates.
- [x] 6.2 Expand `backend/tests/test_homography.py` to cover rectangle mapping, `image_to_court`, `court_to_image`, batch transforms, and invalid input errors.
- [x] 6.3 Add or update API tests for manual calibration creation and calibration retrieval.
- [x] 6.4 Add a lightweight overlay test using an in-memory frame if OpenCV is available in the test environment.
- [x] 6.5 Run the backend pytest suite from `backend/` and resolve regressions.
