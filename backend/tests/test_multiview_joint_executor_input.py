from app.services.multiview_joint_executor import _deserialize_joint_view_input


def test_deserialize_joint_view_input_accepts_persisted_camel_case_payload():
    view = _deserialize_joint_view_input(
        {
            "cameraSlot": "cam_1",
            "captureTrackId": "track-1",
            "cameraId": "174",
            "videoId": "rec-1",
            "calibrationId": "calib-1",
            "courtOrientation": "identity",
        }
    )

    assert view.camera_slot == "cam_1"
    assert view.capture_track_id == "track-1"
    assert view.camera_id == "174"
    assert view.video_id == "rec-1"
    assert view.calibration_id == "calib-1"
    assert view.court_orientation == "identity"


def test_deserialize_joint_view_input_preserves_internal_snake_case_payload():
    view = _deserialize_joint_view_input(
        {
            "camera_slot": "cam_2",
            "camera_id": "175",
            "video_id": "rec-2",
            "calibration_id": "calib-2",
            "court_orientation": "rotate_180",
        }
    )

    assert view.camera_slot == "cam_2"
    assert view.camera_id == "175"
    assert view.video_id == "rec-2"
    assert view.calibration_id == "calib-2"
    assert view.court_orientation == "rotate_180"
