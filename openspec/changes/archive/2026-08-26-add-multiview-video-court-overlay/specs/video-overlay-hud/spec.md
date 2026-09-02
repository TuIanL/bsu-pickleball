# video-overlay-hud Specification Delta

## MODIFIED Requirements

### Requirement: 比例正确且视频友好的球场 HUD

系统 SHALL 在真实视频分析播放区域内提供半透明、可读且不遮挡主要视频内容的空间 HUD。空间 HUD SHALL 同时支持俯视球场 HUD 和基于当前机位真实标定的主视频投影层：俯视 HUD 使用标准匹克球场几何保持 20×44 英尺的纵横比，正式球场 SHALL 比 tracking bounds 更突出；主视频投影层 SHALL 使用当前视频的同一 `viewBox` 对齐真实画面。俯视 HUD SHALL 默认收起，仅在用户主动展开时显示；主视频球场与球网投影 SHALL 由独立图层控制，且不遮挡底部播放控件。

#### Scenario: 桌面视频显示 HUD

- **WHEN** 用户打开包含球员投影轨迹的真实分析视频
- **THEN** 视频右上侧显示球场 HUD 展开按钮，正式球场线、球网、厨房区和边界图例清晰可辨，且 HUD 不覆盖底部播放控件
- **AND** 若当前机位标定资产可用，主视频可显示与画面重合的球场/球网投影层

#### Scenario: 窄屏视频显示 HUD

- **WHEN** 用户在窄屏设备上打开真实分析视频
- **THEN** HUD 缩放或调整位置以保持球场比例，并且不与视频时间、播放按钮或图层控制发生重叠
- **AND** 主视频投影 SHALL 随视频 `preserveAspectRatio` 保持对齐

#### Scenario: HUD 默认收起

- **WHEN** 用户打开真实分析视频且尚未主动展开球场 HUD
- **THEN** 只显示地图展开按钮，不显示完整俯视球场 HUD，避免遮挡视频与播放控件
- **AND** 主视频投影层是否显示由球场/球网投影开关独立决定

#### Scenario: 用户展开 HUD 后再次收起

- **WHEN** 用户点击地图展开按钮显示 HUD，再次点击同一按钮
- **THEN** HUD 收起，只保留展开按钮，且视频播放状态与图层状态保持不变

#### Scenario: HUD 不显示 tracking bounds

- **WHEN** 当前设置关闭边界诊断或没有有效越界点
- **THEN** HUD 仍显示正式球场，不因隐藏 tracking bounds 而改变正式球场的比例或位置

#### Scenario: 主视频标定资产不可用

- **WHEN** 当前 view 缺少有效的 court calibration 或球网人工标注
- **THEN** 对应的主视频投影层 SHALL 隐藏并显示可解释的不可用状态
- **AND** 俯视 HUD、人物框、骨架、球点、球路和播放控件 SHALL 继续按各自资产状态工作
