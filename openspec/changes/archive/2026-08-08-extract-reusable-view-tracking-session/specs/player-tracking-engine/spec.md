# player-tracking-engine Delta

## ADDED Requirements

### Requirement: 可选 ROI 检测契约 detect_regions

`PersonDetector` SHALL 提供方法 `detect_regions(frame, regions, confidence_override=None) -> list[Detection]`，对指定的图像 ROI 区域执行检测并返回源帧坐标系检测框。该方法 SHALL 为可选能力：未实现 ROI 推理的实现 SHALL 显式抛出 `RegionDetectionUnsupported`（并提供 `supports_region_detection = False`），SHALL NOT 用空列表静默表示"不支持"；`EmptyPersonDetector` SHALL 返回空列表（其语义为"永无检测"）。新增方法 SHALL NOT 改变现有 `detect` / `detect_frame` 行为。

#### Scenario: 未实现 ROI 推理显式报错

- **WHEN** 调用 `detect_regions` 于未实现 ROI 推理的 `PersonDetector` 实现
- **THEN** 系统 SHALL 抛出 `RegionDetectionUnsupported`
- **AND** `supports_region_detection` SHALL 为 False

#### Scenario: EmptyPersonDetector 返回空

- **WHEN** 调用 `detect_regions` 于 `EmptyPersonDetector`
- **THEN** 返回空列表且不抛异常

#### Scenario: 不影响现有接口

- **WHEN** 使用 `detect` / `detect_frame`
- **THEN** 行为 SHALL 与实现 `detect_regions` 之前完全一致

#### Scenario: ROI 结果坐标语义（P1 预留）

- **WHEN** 某实现返回 ROI 检测结果
- **THEN** 检测框坐标 SHALL 为源帧坐标系（非 ROI-local 坐标），与现有检测输出可互换
