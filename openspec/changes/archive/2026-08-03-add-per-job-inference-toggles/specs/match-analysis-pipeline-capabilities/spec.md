## ADDED Requirements

### Requirement: Task-level inference toggles drive pipeline execution
The system SHALL honor per-job inference toggles when executing an analysis pipeline, overriding the global configuration for that job while preserving the global defaults for jobs that do not specify toggles.

#### Scenario: Job enables model inference
- **WHEN** an analysis job carries `enableModelInference=true`
- **THEN** the pipeline SHALL run YOLO human detection with the configured detector model for that job even if the global setting is disabled

#### Scenario: Job disables model inference
- **WHEN** an analysis job carries `enableModelInference=false`
- **THEN** the pipeline SHALL use the empty detector behavior (no human boxes, detection stage skipped) and SHALL NOT run model inference

#### Scenario: Job enables pose inference
- **WHEN** an analysis job carries `enablePoseInference=true` and the RTMPose config/checkpoint are resolvable
- **THEN** the pipeline SHALL run RTMPose pose estimation for that job even if the global setting is disabled

#### Scenario: Job disables pose inference
- **WHEN** an analysis job carries `enablePoseInference=false`
- **THEN** the pipeline SHALL skip pose estimation and report the pose overlay as unavailable

#### Scenario: Toggle omitted falls back to global config
- **WHEN** an analysis job does not specify `enableModelInference` or `enablePoseInference`
- **THEN** the pipeline SHALL use the backend global configuration for those switches

#### Scenario: Toggles participate in job deduplication
- **WHEN** two job submissions share the same input but differ in `enableModelInference` or `enablePoseInference`
- **THEN** the configuration signature SHALL differ so the jobs are not deduplicated into one
