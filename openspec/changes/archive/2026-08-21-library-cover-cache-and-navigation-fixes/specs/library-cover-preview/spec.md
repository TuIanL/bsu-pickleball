## ADDED Requirements

### Requirement: 封面会话内缓存

比赛库卡片封面的首帧 SHALL 在浏览器会话内被缓存（module 级 dataURL），供跨路由往返复用，避免重复解码视频流。

#### Scenario: 返回比赛库立即显示已加载封面
- **WHEN** 用户首次打开比赛库，某封面已解码并写入缓存
- **AND** 用户切换到其它页面再返回比赛库
- **THEN** 该封面 SHALL 直接以缓存 `<img>` 显示，无需重新请求视频流解码

#### Scenario: 未命中缓存时解码并落缓存
- **WHEN** 某封面stream URL 尚未在缓存中
- **THEN** 卡片 SHALL 渲染临时 `<video>` 解码约 0.05s 的帧，绘制为小型 jpeg dataURL 写入缓存
- **AND** 随后以 `<img>` 展示并卸载临时 `<video>`

#### Scenario: 缓存有界
- **WHEN** 缓存条目数超过上限
- **THEN** 系统 SHALL 按 LRU 淘汰最久未用条目，避免内存无限增长

### Requirement: 封面渲染按来源分派

封面渲染 SHALL 依据素材来源分派布局：单摄/上传为单画面，双摄为左右双机位拼接。

#### Scenario: 单摄或上传封面
- **WHEN** 素材的 `sourceType` 为 `recording`（单摄）或 `upload`
- **THEN** 封面 SHALL 以单画面 `object-cover` 全幅显示

#### Scenario: 双摄封面左右拼接
- **WHEN** 素材 `cameraSetup` 为 `dual` 且两路机位流可用
- **THEN** 封面 SHALL 将 `cam_1`（左）与 `cam_2`（右）各占半幅 `object-cover` 拼接显示，裁掉黑边
- **AND** 封面 SHALL 带「双摄」标识，使用户一眼识别为双视角联动任务

#### Scenario: 双摄某一路流缺失
- **WHEN** 素材为双摄但仅有一路机位流可用
- **THEN** 缺失那一半 SHALL 显示中性占位，不伪造画面

## REMOVED Requirements

（无）