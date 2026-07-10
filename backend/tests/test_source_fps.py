from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
from app.services.job_orchestration import analysis_signature
from app.utils.fps import frames_for_seconds, resolve_effective_fps
from app.vision.pickleball_game_analysis.bounce_detector import BounceDetector, BounceDetectorConfig


def _metadata(source_fps: float | None = None) -> AnalysisUploadMetadata:
    return AnalysisUploadMetadata(
        fileName="match.mp4",
        sourceFps=source_fps,
        matchTitle="Match",
        venue="Court",
        matchDate="2026-07-10",
        matchFormat="doubles",
        cameraAngle="elevated",
        athleteLabel="A",
        level="club",
    )


def test_effective_fps_prefers_user_then_metadata_then_fallback():
    assert resolve_effective_fps(90, 30).effective_fps == 90
    assert resolve_effective_fps(None, 60).effective_fps == 60

    fallback = resolve_effective_fps(None, 0)
    assert fallback.effective_fps == 30
    assert fallback.fps_source == "fallback"


def test_analysis_signature_includes_source_fps():
    base = AnalysisJobCreate(metadata=_metadata(30), videoId="video-1", calibrationId="cal-1")
    changed = AnalysisJobCreate(metadata=_metadata(90), videoId="video-1", calibrationId="cal-1")

    assert analysis_signature(base) != analysis_signature(changed)


def test_frames_for_seconds_scales_with_fps():
    assert frames_for_seconds(2.0, 30) == 60
    assert frames_for_seconds(2.0, 60) == 120
    assert frames_for_seconds(2.0, 90) == 180
    assert frames_for_seconds(2.0, 120) == 240


def test_bounce_detector_event_gap_uses_effective_fps():
    detector_30 = BounceDetector(BounceDetectorConfig(fps=30, min_event_gap_sec=0.25))
    detector_120 = BounceDetector(BounceDetectorConfig(fps=120, min_event_gap_sec=0.25))

    assert detector_30.min_event_gap_frames == 7
    assert detector_120.min_event_gap_frames == 30


def test_ball_velocity_uses_effective_fps():
    detector = BounceDetector(BounceDetectorConfig(fps=90))
    velocity = detector._velocity(__import__("numpy").array([[0, 0], [10, 0]], dtype="float32"))

    assert velocity[1] == 900
