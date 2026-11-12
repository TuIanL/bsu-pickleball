# Target-subject provider contract v1

This directory vendors the public provider schemas and fixtures owned by `pickleball-action-dataset`. Provider contract tests read only these files and do not import dataset code or state.

When the contract changes, copy all schemas, fixtures, and `contract_bundle.sha256.json` together. A Pilot or formal run must pin the contract version and the effective schema hashes in its run metadata.

包内镜像位于 `app/vision/target_subject_provider/contract_data/v1`。更新本目录时同时同步全部JSON；回归测试校验两份文件集合、内容及摘要一致。运行时仅通过包资源读取镜像，使wheel和sdist在离开源码后仍可校验。新增可选 `configuration.tracker_algorithm` 支持 `motion`/`legacy`；省略时固定 `motion`，旧请求继续兼容。
