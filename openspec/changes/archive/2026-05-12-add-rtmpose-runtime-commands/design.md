## Context

The backend already documents `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` for trusted OpenMMLab RTMPose checkpoints, and the repository contains local RTMPose config/checkpoint paths under `models/rtmpose/`. The manual workflow still requires remembering backend environment variables, starting the backend, starting Vite, and later finding the right processes to stop.

## Goals / Non-Goals

**Goals:**
- Provide a single command that starts the local backend with RTMPose-safe environment variables and starts the frontend dev server.
- Provide a single command that stops the processes created by the startup command.
- Keep commands transparent shell scripts that work on the project's macOS development environment.

**Non-Goals:**
- Add a production process manager.
- Change RTMPose model loading internals.
- Download model assets or install dependencies automatically.
- Replace manual backend/frontend commands for advanced debugging.

## Decisions

- Use repository-local shell scripts under `scripts/` so the commands do not require a new dependency.
- Store runtime PIDs under `.runtime/`, which is ignored by git, so shutdown can target processes started by this project.
- Add macOS `.command` wrappers for double-click usage and package scripts for terminal usage.
- Start backend and frontend in the background with logs written to `.runtime/logs/`, making failures inspectable without keeping two terminals open.
- Prefer explicit RTMPose environment defaults in the startup script while allowing caller-provided overrides.

## Risks / Trade-offs

- [Risk] A process may crash before shutdown runs. -> Mitigation: shutdown ignores stale PIDs and removes stale PID files.
- [Risk] A port conflict can prevent startup. -> Mitigation: startup checks ports before launching and points users at the shutdown command.
- [Risk] `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` lowers PyTorch checkpoint loading restrictions. -> Mitigation: only set it for the local trusted OpenMMLab checkpoint workflow already documented in the project.
