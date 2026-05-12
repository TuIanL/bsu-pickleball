## Why

RTMPose skeleton inference currently fails on PyTorch 2.6+ unless the trusted OpenMMLab checkpoint is loaded with the documented runtime override. Developers also have to retype several backend and frontend commands every time they want to run the local analysis stack.

## What Changes

- Add one-command local startup for the RTMPose-enabled backend and Vite frontend.
- Add one-command local shutdown for processes started by the startup command.
- Ensure the startup command sets the RTMPose checkpoint paths and `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` so trusted OpenMMLab checkpoints load under modern PyTorch.
- Document the commands and their assumptions.

## Capabilities

### New Capabilities
- `local-runtime-commands`: Local developer commands for starting and stopping the RTMPose-enabled analysis runtime.

### Modified Capabilities

## Impact

- Adds local developer scripts and package scripts.
- Updates documentation for running and stopping the local app.
- Does not change production APIs, model inference behavior, or frontend report contracts.
