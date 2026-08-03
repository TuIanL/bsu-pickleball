# 源码中文注释审计

- 扫描代码文件总数: **365**
- 含中文注释/文档: **232**
- 无中文注释/文档: **133**

## 无中文注释/文档的文件


### backend/ (44)

- `backend/alembic_migrations/versions/9a4b2c8d3e6f_add_scoring_fields_to_live_coding_state.py`
- `backend/alembic_migrations/versions/b8e4c2d1f607_add_hybrid_match_scoring_state.py`
- `backend/alembic_migrations/versions/d4e5f6a7b8c9_add_vidat_annotation_packages.py`
- `backend/alembic_migrations/versions/e1d0cca8a2e5_add_segment_edit_operations_and_.py`
- `backend/alembic_migrations/versions/e5f6a7b8c9d0_add_vidat_provenance.py`
- `backend/app/models/field_session.py`
- `backend/app/services/dual_camera_sync.py`
- `backend/app/services/scoring_fsm.py`
- `backend/app/services/vidat_server.py`
- `backend/app/utils/fps.py`
- `backend/app/vision/pickleball_game_analysis/ball_detector_protocol.py`
- `backend/scripts/align_dual_camera_media.py`
- `backend/scripts/calibrate_dual_camera_sync.py`
- `backend/scripts/export_dual_camera_annotations.py`
- `backend/tests/test_action_classification_preprocessing.py`
- `backend/tests/test_api_smoke.py`
- `backend/tests/test_automatic_court_calibration.py`
- `backend/tests/test_ball_game_analysis.py`
- `backend/tests/test_ball_tracker_lock_gating.py`
- `backend/tests/test_capture_storage.py`
- `backend/tests/test_coco_dataset_validation.py`
- `backend/tests/test_config.py`
- `backend/tests/test_court_geometry.py`
- `backend/tests/test_court_overlay.py`
- `backend/tests/test_court_track_postprocessor.py`
- `backend/tests/test_court_view_roi.py`
- `backend/tests/test_dual_camera_sync.py`
- `backend/tests/test_field_sessions.py`
- `backend/tests/test_footpoint_projection.py`
- `backend/tests/test_homography.py`
- `backend/tests/test_hybrid_coding_actions.py`
- `backend/tests/test_match_format_analysis.py`
- `backend/tests/test_metrics.py`
- `backend/tests/test_multitarget_perception.py`
- `backend/tests/test_player_identity.py`
- `backend/tests/test_primary_player_selector.py`
- `backend/tests/test_real_video_frame_extraction.py`
- `backend/tests/test_recorder.py`
- `backend/tests/test_rtmpose26_adapter.py`
- `backend/tests/test_serve_start_detection.py`
- `backend/tests/test_source_fps.py`
- `backend/tests/test_vidat_annotation_service.py`
- `backend/tests/test_vidat_cli.py`
- `backend/tests/test_visualization_outputs.py`

### eslint.config.js/ (1)

- `eslint.config.js`

### index.html/ (1)

- `index.html`

### models/ (1)

- `models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py`

### scripts/ (3)

- `scripts/start-local-runtime.sh`
- `scripts/stop-local-runtime.sh`
- `scripts/train-court-line-windows.ps1`

### src/ (81)

- `src/app/AppRouter.tsx`
- `src/app/navigationTypes.ts`
- `src/app/router.test.ts`
- `src/app/router.ts`
- `src/components/AppHeader.tsx`
- `src/components/DiagnosisSection.tsx`
- `src/components/DiagnosticNoticeCard.tsx`
- `src/components/Field.tsx`
- `src/components/FusionBlock.tsx`
- `src/components/HardwareFusionPreview.tsx`
- `src/components/MetricStrip.tsx`
- `src/components/MiniTimeline.test.ts`
- `src/components/MiniTimeline.test.tsx`
- `src/components/PageFrame.tsx`
- `src/components/ProjectionReadiness.tsx`
- `src/components/RailMeta.tsx`
- `src/components/RecommendedDrills.tsx`
- `src/components/ScoreBoard.test.tsx`
- `src/components/SegmentVideoPlayer.tsx`
- `src/components/StatusState.tsx`
- `src/components/TaskMeta.tsx`
- `src/components/TrainingLoop.tsx`
- `src/components/capture/CameraInfoCard.tsx`
- `src/components/capture/CameraPreviewCard.tsx`
- `src/components/capture/CaptureWorkspaceHeader.tsx`
- `src/components/capture/CaptureWorkspaceLayout.tsx`
- `src/components/capture/CompactScoreStrip.test.tsx`
- `src/components/capture/CompactScoreStrip.tsx`
- `src/components/capture/EventActionToolbar.test.tsx`
- `src/components/capture/EventActionToolbar.tsx`
- `src/components/capture/RecentEventsCard.tsx`
- `src/components/capture/RecordingControlPanel.tsx`
- `src/components/capture/VidatWorkbenchPanel.test.tsx`
- `src/components/capture/VidatWorkbenchPanel.tsx`
- `src/components/capture/captureClock.test.ts`
- `src/components/capture/captureClock.ts`
- `src/components/capture/captureTypes.ts`
- `src/components/capture/eventLabels.test.ts`
- `src/components/capture/eventLabels.ts`
- `src/components/capture/timelineScale.test.ts`
- `src/components/capture/timelineScale.ts`
- `src/components/platform/AppShell.tsx`
- `src/components/platform/AppSidebar.tsx`
- `src/components/platform/FieldSessionGroupCard.tsx`
- `src/components/platform/MetricCard.tsx`
- `src/components/platform/ProgressChart.tsx`
- `src/components/platform/RecordingTaskCard.tsx`
- `src/components/platform/ReportVisualization.tsx`
- `src/components/platform/SkillRatings.tsx`
- `src/components/platform/StructuredHeatmap.tsx`
- `src/components/platform/StructuredScatterPlot.tsx`
- `src/components/platform/serveMarkers.test.ts`
- `src/hooks/useActiveCaptureTake.ts`
- `src/hooks/useCaptureRuntime.test.ts`
- `src/index.css`
- `src/pages/AnalysisDetailsPage.tsx`
- `src/pages/AnalysisJobPage.tsx`
- `src/pages/CaptureConsolePage.behavior.test.tsx`
- `src/pages/CaptureConsolePage.test.tsx`
- `src/pages/HardwarePage.tsx`
- `src/pages/RecordingWorkspacePage.test.ts`
- `src/pages/ReportPage.tsx`
- `src/pages/TrainingPage.tsx`
- `src/pages/dualCameraCapture.test.ts`
- `src/services/analysisClient.ts`
- `src/services/analysisDiagnostics.test.ts`
- `src/services/analysisDiagnostics.ts`
- `src/services/captureAdapter.test.ts`
- `src/services/codingOutbox.test.ts`
- `src/services/courtProjectionTracks.test.ts`
- `src/services/courtProjectionTracks.ts`
- `src/services/matchControlViewModel.test.ts`
- `src/services/matchControlViewModel.ts`
- `src/services/playerRenderTrajectory.test.ts`
- `src/services/playerRenderTrajectory.ts`
- `src/services/sourceFps.test.ts`
- `src/services/syncMergeState.ts`
- `src/services/timelineQuickEvents.test.ts`
- `src/styles/app.css`
- `src/utils/analysisHelpers.ts`
- `src/vite-env.d.ts`

### tailwind.config.ts/ (1)

- `tailwind.config.ts`

### vite.config.ts/ (1)

- `vite.config.ts`

## 含中文注释/文档的文件


### backend/ (187)

- `backend/alembic_migrations/env.py`
- `backend/alembic_migrations/versions/7f3a2c1d9b4e_add_capture_storage_location.py`
- `backend/alembic_migrations/versions/cc7c84e75e78_add_capture_take_and_coding_console.py`
- `backend/app/__init__.py`
- `backend/app/api/__init__.py`
- `backend/app/api/analysis.py`
- `backend/app/api/routes_analysis.py`
- `backend/app/api/routes_calibration.py`
- `backend/app/api/routes_camera.py`
- `backend/app/api/routes_coding_actions.py`
- `backend/app/api/routes_field_sessions.py`
- `backend/app/api/routes_recording.py`
- `backend/app/api/routes_segment_editing.py`
- `backend/app/api/routes_storage.py`
- `backend/app/api/routes_sync_recording.py`
- `backend/app/api/routes_timeline_events.py`
- `backend/app/api/routes_vidat.py`
- `backend/app/api/routes_video.py`
- `backend/app/camera/__init__.py`
- `backend/app/camera/camera_lease_service.py`
- `backend/app/camera/camera_registry.py`
- `backend/app/camera/capture_completion_service.py`
- `backend/app/camera/capture_finalizer.py`
- `backend/app/camera/capture_recovery.py`
- `backend/app/camera/capture_runtime_coordinator.py`
- `backend/app/camera/ffmpeg_utils.py`
- `backend/app/camera/models.py`
- `backend/app/camera/preflight_adapters.py`
- `backend/app/camera/preview_service.py`
- `backend/app/camera/recorder.py`
- `backend/app/camera/recorder_exit.py`
- `backend/app/camera/recording_impl.py`
- `backend/app/camera/recording_policy.py`
- `backend/app/camera/recording_protocols.py`
- `backend/app/camera/session_service.py`
- `backend/app/camera/stream_probe.py`
- `backend/app/camera/sync_recorder_service.py`
- `backend/app/camera/track_recorder.py`
- `backend/app/core/__init__.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/database.py`
- `backend/app/main.py`
- `backend/app/models/analysis_batch.py`
- `backend/app/models/camera_lease.py`
- `backend/app/models/capture_coding_action.py`
- `backend/app/models/capture_segment.py`
- `backend/app/models/capture_take.py`
- `backend/app/models/capture_track.py`
- `backend/app/models/ffmpeg_registry.py`
- `backend/app/models/live_coding_state.py`
- `backend/app/models/media_fragment.py`
- `backend/app/models/segment_edit_operation.py`
- `backend/app/models/timeline_event.py`
- `backend/app/models/track_finalization.py`
- `backend/app/models/track_timeline_span.py`
- `backend/app/models/vidat_annotation.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/analysis.py`
- `backend/app/schemas/ball.py`
- `backend/app/schemas/calibration.py`
- `backend/app/schemas/capture_runtime_status.py`
- `backend/app/schemas/capture_stop_result.py`
- `backend/app/schemas/capture_take_summary.py`
- `backend/app/schemas/coding_actions.py`
- `backend/app/schemas/court_view.py`
- `backend/app/schemas/events.py`
- `backend/app/schemas/field_session.py`
- `backend/app/schemas/metrics.py`
- `backend/app/schemas/multitarget.py`
- `backend/app/schemas/pipeline.py`
- `backend/app/schemas/pose.py`
- `backend/app/schemas/timeline_event.py`
- `backend/app/schemas/tracking.py`
- `backend/app/schemas/video.py`
- `backend/app/services/__init__.py`
- `backend/app/services/analysis_batch_service.py`
- `backend/app/services/analysis_pipeline.py`
- `backend/app/services/automatic_calibration_service.py`
- `backend/app/services/calibration_service.py`
- `backend/app/services/capture_archive_service.py`
- `backend/app/services/capture_cleanup_service.py`
- `backend/app/services/capture_coding_action_service.py`
- `backend/app/services/capture_runtime_status_service.py`
- `backend/app/services/capture_segment_service.py`
- `backend/app/services/capture_start_coordinator.py`
- `backend/app/services/capture_storage_service.py`
- `backend/app/services/capture_take_service.py`
- `backend/app/services/capture_track_service.py`
- `backend/app/services/coding_actions_service.py`
- `backend/app/services/field_session_service.py`
- `backend/app/services/job_orchestration.py`
- `backend/app/services/live_coding_state_service.py`
- `backend/app/services/mock_analysis.py`
- `backend/app/services/segment_edit_service.py`
- `backend/app/services/storage_service.py`
- `backend/app/services/timeline_event_service.py`
- `backend/app/services/vidat_annotation_service.py`
- `backend/app/services/video_service.py`
- `backend/app/vision/__init__.py`
- `backend/app/vision/action_classification_preprocessing/__init__.py`
- `backend/app/vision/action_classification_preprocessing/exporter.py`
- `backend/app/vision/action_classification_preprocessing/preprocessing.py`
- `backend/app/vision/action_classification_preprocessing/schemas.py`
- `backend/app/vision/action_classification_preprocessing/selection.py`
- `backend/app/vision/court/__init__.py`
- `backend/app/vision/court/base.py`
- `backend/app/vision/court_view.py`
- `backend/app/vision/courtvision_calibration_engine/__init__.py`
- `backend/app/vision/courtvision_calibration_engine/coco_dataset.py`
- `backend/app/vision/courtvision_calibration_engine/court_geometry.py`
- `backend/app/vision/courtvision_calibration_engine/court_line_segmentation.py`
- `backend/app/vision/courtvision_calibration_engine/court_overlay.py`
- `backend/app/vision/courtvision_calibration_engine/court_units.py`
- `backend/app/vision/courtvision_calibration_engine/homography.py`
- `backend/app/vision/courtvision_calibration_engine/manual_keypoint_calibrator.py`
- `backend/app/vision/courtvision_calibration_engine/mask_to_keypoints.py`
- `backend/app/vision/courtvision_calibration_engine/real_video_frame_extraction.py`
- `backend/app/vision/courtvision_calibration_engine/reference_line_support.py`
- `backend/app/vision/detectors/__init__.py`
- `backend/app/vision/detectors/ball_adapter.py`
- `backend/app/vision/detectors/base.py`
- `backend/app/vision/detectors/multitarget.py`
- `backend/app/vision/detectors/yolo11_adapter.py`
- `backend/app/vision/events/__init__.py`
- `backend/app/vision/events/serve_start_detector.py`
- `backend/app/vision/pickleball_game_analysis/__init__.py`
- `backend/app/vision/pickleball_game_analysis/ball_tracker.py`
- `backend/app/vision/pickleball_game_analysis/bounce_detector.py`
- `backend/app/vision/pickleball_game_analysis/calibration_diagnostics.py`
- `backend/app/vision/pickleball_game_analysis/court_adapter.py`
- `backend/app/vision/pickleball_game_analysis/court_track_postprocessor.py`
- `backend/app/vision/pickleball_game_analysis/court_track_types.py`
- `backend/app/vision/pickleball_game_analysis/detection_writer.py`
- `backend/app/vision/pickleball_game_analysis/minimap_visualizer.py`
- `backend/app/vision/pickleball_game_analysis/overlay_video_writer.py`
- `backend/app/vision/pickleball_game_analysis/position_visualizer.py`
- `backend/app/vision/pickleball_game_analysis/projection_debug_overlay_writer.py`
- `backend/app/vision/pickleball_game_analysis/projection_debug_writer.py`
- `backend/app/vision/pickleball_game_analysis/schemas.py`
- `backend/app/vision/pickleball_game_analysis/trajectory_cleaner.py`
- `backend/app/vision/pickleball_game_analysis/visualization_data_builder.py`
- `backend/app/vision/pickleball_game_analysis/visualization_schemas.py`
- `backend/app/vision/pickleball_performance_engine/__init__.py`
- `backend/app/vision/pickleball_performance_engine/doubles_spacing_metrics.py`
- `backend/app/vision/pickleball_performance_engine/heatmap_generator.py`
- `backend/app/vision/pickleball_performance_engine/metric_inputs.py`
- `backend/app/vision/pickleball_performance_engine/speed_metrics.py`
- `backend/app/vision/pickleball_performance_engine/trajectory_metrics.py`
- `backend/app/vision/pickleball_performance_engine/zone_metrics.py`
- `backend/app/vision/player_tracking_engine/__init__.py`
- `backend/app/vision/player_tracking_engine/attention_player_selector.py`
- `backend/app/vision/player_tracking_engine/court_position_smoother.py`
- `backend/app/vision/player_tracking_engine/footpoint_estimator.py`
- `backend/app/vision/player_tracking_engine/multi_object_tracker.py`
- `backend/app/vision/player_tracking_engine/person_detector.py`
- `backend/app/vision/player_tracking_engine/player_identity.py`
- `backend/app/vision/player_tracking_engine/player_lock_manager.py`
- `backend/app/vision/player_tracking_engine/player_lock_types.py`
- `backend/app/vision/player_tracking_engine/player_projector.py`
- `backend/app/vision/player_tracking_engine/primary_player_selector.py`
- `backend/app/vision/pose/__init__.py`
- `backend/app/vision/pose/base.py`
- `backend/app/vision/pose/rtmpose26_adapter.py`
- `backend/app/vision/tracking/__init__.py`
- `backend/app/vision/tracking/base.py`
- `backend/scripts/export_action_classification_dataset.py`
- `backend/scripts/export_pose_overlay_video.py`
- `backend/scripts/export_swing_skeleton.py`
- `backend/scripts/extract_real_video_frames.py`
- `backend/scripts/train_attention_player_selector.py`
- `backend/scripts/train_court_line_segmentation.py`
- `backend/scripts/validate_coco_segmentation.py`
- `backend/scripts/validate_rtmpose.py`
- `backend/tests/fake_services.py`
- `backend/tests/test_analysis_pipeline_ball.py`
- `backend/tests/test_ball_tracker_stationary_blacklist.py`
- `backend/tests/test_capture_runtime_status.py`
- `backend/tests/test_coding_actions.py`
- `backend/tests/test_court_projection_bounds.py`
- `backend/tests/test_recording_lifecycle.py`
- `backend/tests/test_rtmpose_hysteresis.py`
- `backend/tests/test_scoring_fsm.py`
- `backend/tests/test_segment_editing.py`
- `backend/tests/test_sync_recording.py`
- `backend/tests/test_timeline_events.py`
- `backend/tests/test_track_recorder.py`

### models/ (3)

- `models/rtmpose/configs/_base_/default_runtime.py`
- `models/rtmpose/configs/body_2d_keypoint/_base_/default_runtime.py`
- `models/rtmpose/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py`

### scripts/ (3)

- `scripts/export_to_vidat.py`
- `scripts/import_from_vidat.py`
- `scripts/vidat_workbench.py`

### src/ (39)

- `src/App.tsx`
- `src/components/EditableSegmentTimeline.tsx`
- `src/components/MiniTimeline.tsx`
- `src/components/ScoreBoard.tsx`
- `src/components/capture/SystemStatusCard.tsx`
- `src/components/platform/CourtMinimap.tsx`
- `src/components/platform/FieldSessionGroupCard.test.tsx`
- `src/components/platform/Modal.tsx`
- `src/components/platform/VideoAnalysisCard.tsx`
- `src/components/platform/videoOverlayPlayback.ts`
- `src/hooks/useCameraSetup.ts`
- `src/hooks/useCapturePreflight.ts`
- `src/hooks/useCaptureRuntime.ts`
- `src/hooks/useCaptureRuntimeStatus.test.ts`
- `src/hooks/useCaptureRuntimeStatus.ts`
- `src/hooks/useLiveCoding.ts`
- `src/main.tsx`
- `src/pages/AnalysisTasksPage.tsx`
- `src/pages/CameraHubPage.tsx`
- `src/pages/CaptureConsolePage.tsx`
- `src/pages/CaptureHomePage.tsx`
- `src/pages/CaptureWizardPage.tsx`
- `src/pages/LandingPage.tsx`
- `src/pages/NewAnalysisPage.tsx`
- `src/pages/RecordingWorkspacePage.tsx`
- `src/pages/SegmentManagerPage.tsx`
- `src/pages/VisionPage.tsx`
- `src/services/captureAdapter.ts`
- `src/services/codingOutbox.ts`
- `src/services/pipelineReportAdapter.ts`
- `src/services/recordingGrouping.test.ts`
- `src/services/recordingGrouping.ts`
- `src/services/timelineQuickEvents.ts`
- `src/types/capture.ts`
- `src/types/captureRuntimeStatus.ts`
- `src/types/report.ts`
- `src/utils/courtGeometry.ts`
