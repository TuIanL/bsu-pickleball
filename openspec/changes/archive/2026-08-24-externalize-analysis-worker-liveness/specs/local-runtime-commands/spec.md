## MODIFIED Requirements

### Requirement: One-command local startup

The project SHALL provide a single local command that starts the RTMPose-enabled backend API, an independent analysis-worker process, and the frontend development server for local analysis work.

#### Scenario: Start command launches runtime

- **WHEN** a developer runs the local startup command from the repository
- **THEN** the command starts the backend API with RTMPose inference enabled, trusted checkpoint loading configured, repository-local RTMPose asset paths supplied, and embedded analysis Worker disabled
- **THEN** the command starts an independent analysis-worker process with the same analysis environment
- **THEN** the command starts the frontend development server
- **THEN** the command records separate API, Worker and frontend process information

#### Scenario: Start command detects occupied ports

- **WHEN** the backend or frontend port required by the local startup command is already occupied
- **THEN** the command fails before launching new processes and reports the conflicting port

#### Scenario: API reload does not restart Worker

- **WHEN** the backend API reloads due to a source change
- **THEN** the independent analysis-worker process SHALL remain running
- **AND** its PID and log files SHALL remain valid for the matching shutdown command

### Requirement: One-command local shutdown

The project SHALL provide a single local command that stops the local analysis-worker, backend API and frontend processes launched by the startup command.

#### Scenario: Stop command shuts down runtime

- **WHEN** a developer runs the local shutdown command after using the startup command
- **THEN** the command stops the recorded analysis-worker, backend and frontend processes
- **AND** clears their runtime PID files after successful shutdown

#### Scenario: Stop command handles stale state

- **WHEN** a recorded process is no longer running
- **THEN** the command removes the stale PID file without failing the shutdown workflow

#### Scenario: Worker shutdown is graceful when possible

- **WHEN** the shutdown command sends a normal termination signal to analysis-worker
- **THEN** Worker SHALL stop claiming new jobs and attempt to exit at a safe checkpoint
- **AND** a forced termination SHALL be recoverable by the next startup heartbeat reconciliation

### Requirement: Local runtime documentation

The project SHALL document the separate API/analysis-worker/frontend startup workflow, PID/log locations, external Worker configuration, heartbeat timeout configuration and the distinction between graceful shutdown and interrupted jobs.

#### Scenario: Developer reads runtime docs

- **WHEN** a developer needs to run RTMPose locally
- **THEN** the documentation explains the one-command start and stop workflow, separate process roles, where logs are written and how to inspect Worker liveness
