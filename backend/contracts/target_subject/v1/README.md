# Target-subject provider contract v1

This directory vendors the public provider schemas and fixtures owned by `pickleball-action-dataset`. Provider contract tests read only these files and do not import dataset code or state.

When the contract changes, copy all schemas, fixtures, and `contract_bundle.sha256.json` together. A Pilot or formal run must pin the contract version and the effective schema hashes in its run metadata.
