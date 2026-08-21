# court-constrained-virtual-camera Specification

## Purpose
TBD - created by archiving change add-multiview-3d-ball-reconstruction. Update Purpose after archive.
## Requirements
### Requirement: 由球场 Homography 解算近似虚拟相机
系统 SHALL 为每台摄像机从现有球场平面 Homography 与球场关键点解算一个 `virtual_camera`（近似 pinhole），无需任何真实相机内参标定。至少 4 个球场角点均应参与求解。求解必须基于 **court→image** 方向的矩阵（`inverse_homography`），而非 image→court 方向的 `CalibrationResult.homography`。

#### Scenario: 主点与像素假设
- **WHEN** 系统解算某视角虚拟相机
- **THEN** 主点 SHALL 取画面中心 `(image_width/2, image_height/2)`
- **AND** 像素宽高比 SHALL 视为 1（`fx = fy = f`）
- **AND** `skew` SHALL 视为 0

#### Scenario: 正交约束求焦距与姿态
- **WHEN** 系统利用 `H ≈ K [r1 r2 t]` 与 `r1 ⟂ r2`、`|r1| = |r2|` 约束求解
- **THEN** 系统 SHALL 得到近似焦距 `f` 与近似外参 `(R, t)`
- **AND** 输出 `P_virtual = K [R | t]`

#### Scenario: 球场关键点回投 refine
- **WHEN** 初值得到后
- **THEN** 系统 SHALL 用现有 court keypoints 最小化回投误差对虚拟相机做 refine
- **AND** 输出各视角的 `reprojection_error_px` 作为质量诊断

### Requirement: 双视角虚拟相机落统一 Canonical Court frame
系统 SHALL 使 Cam1 与 Cam2 的虚拟相机工作在同一 CanonicalCourt3DFrame 中，不得因两台摄像机 local court orientation 不同而解析到不一致朝向。

#### Scenario: canonical-to-image 相机链
- **WHEN** 系统构造 Cam_i 的 factorized camera
- **THEN** 相机 SHALL 由 `H_canonical_to_image(cam_i) = canonical_to_local(cam_i) → inverse_homography(cam_i) → image` 构造
- **AND** 两个 `P_virtual` SHALL 落统一 CanonicalCourt3DFrame
- **AND** 不得出现一台把球场 y=0 当近端、另一台当远端的情况

### Requirement: 虚拟相机姿态消歧门
系统 SHALL 对虚拟相机施加姿态消歧，解算不满足时置 `virtual_camera_status = unavailable` 并降级，不得强行生成相机。

#### Scenario: 消歧不合格即降级
- **WHEN** 某视角基线解算未满足下任一条件：所有 court corners 在相机前方、相机 `z > 0`、光轴朝向球场、`R` 近似正交
- **THEN** 该视角 `virtual_camera_status` SHALL 为 `unavailable`
- **AND** 该视角 SHALL 降级 `LANDING_ONLY`（禁止用该 `P` 参与三角测量）

### Requirement: 虚拟相机不做径向畸变
系统 SHALL 使用零径向畸变（`k1 = 0`）模型，不得在虚拟相机求解中引入 `k1` 参数。

#### Scenario: 第一版不引入 k1
- **WHEN** 系统构造虚拟相机
- **THEN** 畸变参数 SHALL 为全零
- **AND** 项目 SHALL 将该能力定位为单独后续 Change，而非在当前阶段补偿。

### Requirement: 虚拟相机显式声明估算性质
系统 SHALL 明确将虚拟相机标注为近似模型，不得声称它为摄像机真实内参。

#### Scenario: 输出带估算标注
- **WHEN** 虚拟相机参与关联/三角测量
- **THEN** 其来源 SHALL 记录为 `homography_constrained_virtual`
- **AND** 文档 SHALL 标注 `approximate`（非 `metric`）。

