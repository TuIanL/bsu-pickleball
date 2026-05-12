## ADDED Requirements

### Requirement: One-command local startup
The project SHALL provide a single local command that starts both the RTMPose-enabled backend and frontend development server for local analysis work.

#### Scenario: Start command launches runtime
- **WHEN** a developer runs the local startup command from the repository
- **THEN** the command starts the backend with RTMPose inference enabled, trusted checkpoint loading configured, and repository-local RTMPose asset paths supplied
- **THEN** the command starts the frontend development server
- **THEN** the command records enough process information for the matching shutdown command

#### Scenario: Start command detects occupied ports
- **WHEN** the backend or frontend port required by the local startup command is already occupied
- **THEN** the command fails before launching new processes and reports the conflicting port

### Requirement: One-command local shutdown
The project SHALL provide a single local command that stops the local backend and frontend processes launched by the startup command.

#### Scenario: Stop command shuts down runtime
- **WHEN** a developer runs the local shutdown command after using the startup command
- **THEN** the command stops the recorded backend and frontend processes and clears their runtime PID files

#### Scenario: Stop command handles stale state
- **WHEN** a recorded process is no longer running
- **THEN** the command removes the stale PID file without failing the shutdown workflow

### Requirement: Local runtime documentation
The project SHALL document how to use the local startup and shutdown commands.

#### Scenario: Developer reads runtime docs
- **WHEN** a developer needs to run RTMPose locally
- **THEN** the documentation explains the one-command start and stop workflow and where logs are written
