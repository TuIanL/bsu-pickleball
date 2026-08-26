## ADDED Requirements

### Requirement: 球网非共面点参与虚拟相机 refinement

系统 SHALL 以现有球场平面 Homography 与球场关键点解算每台摄像机的 baseline virtual camera；当存在 `metric_court_scene.v1` 的可用球网非共面 control points 时，系统 SHALL 使用球场地面点和球网点共同进行相机姿态/内参 refinement。未提供可用场景标定时，系统 SHALL 保留现有近似 pinhole 求解和 fallback，不得静默声称其为 metric 相机。

#### Scenario: 无场景标定时保留 baseline
- **WHEN** 系统只有 `inverse_homography`、court keypoints 和 `court_orientation`
- **THEN** 系统 SHALL 按现有流程生成 `homography_constrained_virtual` 相机
- **AND** 输出 SHALL 标记 `approximate`，不得标记为 `metric`

#### Scenario: 球网非共面点参与 refinement
- **WHEN** 当前采集任务存在状态为 `ready` 的 scene calibration revision
- **THEN** 系统 SHALL 使用该 revision 的球场点和球网三维点共同优化相机模型
- **AND** 输出 SHALL 保存 `scene_calibration_revision` 与 net-assisted camera model source

#### Scenario: 主点与像素假设
- **WHEN** 系统解算 baseline 或 net-assisted virtual camera
- **THEN** 主点 SHALL 取画面中心 `(image_width/2, image_height/2)`
- **AND** 像素宽高比 SHALL 视为 1（`fx = fy = f`）
- **AND** `skew` SHALL 视为 0

#### Scenario: 回投 refinement
- **WHEN** 初值得到后
- **THEN** 系统 SHALL 使用参与拟合的 court/net keypoints 和可用 hold-out points 评估回投误差
- **AND** SHALL 输出各视角的 court residual、net residual 和 overall `reprojection_error_px`
