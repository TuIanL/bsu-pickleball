## Context

The backend already has a Python FastAPI project under `backend/` with an MVP CourtVision package, storage service, calibration service, calibration schemas, and tests. The current CourtVision implementation provides useful placeholders, but it does not yet expose the requested production-shaped calibration workflow: RANSAC homography computation, inverse projection, canonical four-corner request handling, calibration quality metadata, filled overlays, or the `/calibration/...` API shape.

The canonical court coordinate system is fixed for this change: units are feet, x spans 0 to 20, y spans 0 to 44, the net is y = 22, kitchen boundaries are y = 15 and y = 29, and MVP manual calibration uses the four outer court corners.

## Goals / Non-Goals

**Goals:**

- Provide a complete CourtVision Calibration Engine module that can be imported without model weights or automatic vision dependencies.
- Preserve a clear matrix convention: homography maps image pixels to court feet; inverse homography maps court feet back to image pixels.
- Support both single-point and batch-point transforms with validated float coordinates and JSON-serializable matrix outputs.
- Store and retrieve manual calibration results, including inverse homography, coordinate-system metadata, and calibration quality.
- Generate visual overlay previews by projecting standard court geometry into image coordinates.
- Keep existing backend routes and calibration consumers working where practical.

**Non-Goals:**

- Do not implement automatic court-line segmentation or automatic keypoint detection.
- Do not add camera pose estimation, lens calibration, or multi-camera support.
- Do not change downstream tracking or performance metric semantics beyond consuming the richer calibration shape.
- Do not require uploaded sample videos, YOLO, CUDA, or model assets for tests.

## Decisions

### Use `PickleballCourtGeometry` as the primary geometry class with compatibility aliases

The requested module name and class should become the main public API. Existing modules currently import `StandardPickleballCourt` and `standard_court()`, so implementation should either keep those names as aliases or update all consumers in the same change.

Alternative considered: replace `StandardPickleballCourt` outright. This is cleaner internally but creates unnecessary churn in metrics and pipeline modules that already import it.

### Represent geometry as typed points, lines, and polygons

Court lines, keypoints, kitchen zones, and service zones should be returned as deterministic data structures with float coordinates. The geometry class should expose canonical keypoints by name (`top_left`, `top_right`, `bottom_right`, `bottom_left`) and named polygons for the court boundary, kitchens, and left/right service regions.

Alternative considered: return raw dictionaries only. Dictionaries are convenient for JSON but weaker for internal validation and overlay construction.

### Use OpenCV RANSAC for homography computation

`compute_homography(image_points, court_points)` should call `cv2.findHomography(src, dst, cv2.RANSAC)`, validate at least four paired 2D points, reject mismatched or degenerate input, and normalize the returned matrix for stable JSON output.

Alternative considered: keep the current SVD/DLT implementation. That is useful as a fallback but does not satisfy the requested RANSAC behavior and is less robust once 8+ keypoints are supported.

### Add explicit transform functions rather than overloading `project_point`

The engine should expose `image_to_court(point_or_points, H)` and `court_to_image(point_or_points, H_inv)` for the two directions. Existing `project_point` can remain as a compatibility helper that projects one point through any 3x3 homography.

Alternative considered: keep only `project_point`. It hides directionality and makes API call sites easier to misuse.

### Manual calibration accepts named image points and derives court correspondences

For the MVP endpoint, request payloads should accept:

```json
{
  "video_id": "xxx",
  "image_points": {
    "top_left": [x, y],
    "top_right": [x, y],
    "bottom_right": [x, y],
    "bottom_left": [x, y]
  }
}
```

The calibrator should match these names to canonical court keypoints and compute both `homography` and `inverse_homography`. Calibration quality should include reprojection error and a simple status such as `ok` or `warning`.

Alternative considered: require clients to submit full image/court keypoint pairs. The existing API already supports that lower-level shape, but the requested CourtVision UX needs a simpler named-corner contract.

### Add requested `/calibration` routes while keeping `/api/calibrations`

The implementation should expose `/calibration/manual`, `/calibration/{calibration_id}`, and `/calibration/{calibration_id}/preview` for the requested contract. Existing `/api/calibrations` routes should remain available to avoid breaking current README examples and analysis integration.

Alternative considered: migrate all routes to `/calibration`. This would be a breaking API change and is not necessary for the MVP.

### Preview overlay stores generated images under output storage

The preview endpoint should either accept an uploaded frame or derive a first frame from the stored video when available. It should render an overlay image and return a local preview path. If neither frame input nor readable video is available, it should return a clear validation error instead of fabricating an image.

Alternative considered: return raw image bytes only. A stored path matches the requested response and existing backend local artifact conventions.

## Risks / Trade-offs

- OpenCV homography can fail for collinear or badly ordered points → validate names, dimensions, count, and `findHomography` output; return clear 400-level errors through the API.
- Four-corner calibration is sensitive to user click order and camera perspective → use named keys rather than positional arrays and report reprojection error.
- RANSAC with exactly four points has limited outlier rejection → design the data path to accept 8+ named keypoints later without changing transform APIs.
- Overlay polygons can project outside the frame → draw with clipped integer coordinates where OpenCV allows and keep the original frame shape unchanged.
- Introducing new response schemas can diverge from the existing calibration service → centralize calibration creation/storage so old and new routes share the same saved result as much as possible.
