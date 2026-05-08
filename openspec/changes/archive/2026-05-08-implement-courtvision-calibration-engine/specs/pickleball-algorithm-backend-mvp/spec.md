## MODIFIED Requirements

### Requirement: Standard pickleball court geometry
The backend SHALL model a standard pickleball court in a two-dimensional coordinate system measured in feet with width 20, length 44, x spanning 0 to 20, y spanning 0 to 44, net line at y = 22, near kitchen line at y = 15, far kitchen line at y = 29, and center lines for the standard service boxes.

#### Scenario: Court geometry is requested
- **WHEN** code requests the standard court model
- **THEN** the model returns court bounds, outer boundary lines, net line, kitchen lines, center service lines, non-volley zone polygons, and left and right service-zone polygons using the canonical 20 ft by 44 ft coordinates

#### Scenario: Canonical court keypoints are requested
- **WHEN** code requests the standard court keypoints
- **THEN** the model returns float coordinates for `top_left` at `(0, 0)`, `top_right` at `(20, 0)`, `bottom_right` at `(20, 44)`, and `bottom_left` at `(0, 44)`

#### Scenario: Zone membership is evaluated
- **WHEN** a court coordinate is tested against standard zones
- **THEN** the system identifies whether the coordinate is in court bounds, in a kitchen zone, or in a service zone

### Requirement: Manual court calibration and homography
The backend SHALL accept manual or semi-manual court keypoint correspondences, compute a RANSAC-backed homography that maps image pixel coordinates into standard court coordinates, compute the inverse homography that maps standard court coordinates back to image pixel coordinates, and expose validated single-point and batch-point transform helpers.

#### Scenario: Valid calibration is submitted
- **WHEN** at least four valid non-collinear image-to-court point correspondences are submitted
- **THEN** the backend stores the calibration and returns a stable calibration identifier, image-to-court homography matrix, court-to-image inverse homography matrix, court coordinate-system metadata, and calibration quality metadata

#### Scenario: Valid four-corner manual calibration is submitted
- **WHEN** a client submits `/calibration/manual` with `video_id` and named image points for `top_left`, `top_right`, `bottom_right`, and `bottom_left`
- **THEN** the backend automatically matches those points to the standard court outer-corner keypoints and returns JSON-serializable homography, inverse homography, coordinate-system, and quality fields

#### Scenario: Invalid calibration is submitted
- **WHEN** fewer than four correspondences, mismatched point counts, malformed 2D coordinates, or degenerate correspondences are submitted
- **THEN** the backend rejects the calibration with a clear validation error

#### Scenario: Pixel coordinate is projected
- **WHEN** a stored calibration projects an image footpoint
- **THEN** the system returns the corresponding standard court coordinate in feet

#### Scenario: Court coordinate is projected back to the image
- **WHEN** code projects a standard court coordinate through a valid inverse homography
- **THEN** the system returns the corresponding image pixel coordinate as floats

#### Scenario: Batch coordinates are transformed
- **WHEN** code submits multiple image or court coordinates to the transform helpers
- **THEN** the system returns a same-length sequence of transformed float coordinates without changing the requested direction

## ADDED Requirements

### Requirement: Court calibration overlay preview
The backend SHALL render a visual calibration preview by projecting standard court geometry back onto an image frame and drawing the boundary, net line, kitchen boundaries, center service lines, and translucent court-region fills.

#### Scenario: Overlay is drawn on a frame
- **WHEN** a frame image, inverse homography, and standard court geometry are provided
- **THEN** the overlay renderer returns an image with projected outer boundary lines, net line, kitchen lines, center lines, and translucent region fills while preserving the frame dimensions

#### Scenario: Calibration preview is requested
- **WHEN** a client posts to `/calibration/{calibration_id}/preview` with an input frame or a calibration associated with a readable video first frame
- **THEN** the backend generates an overlay preview image artifact and returns its local path

#### Scenario: Calibration preview cannot be generated
- **WHEN** the calibration id is unknown or no usable frame can be read or provided
- **THEN** the backend returns a clear not-found or validation error instead of creating an invalid preview artifact
