## ADDED Requirements

### Requirement: 封面优先使用预生成 poster

当 `LibraryItemViewModel.thumbnailUrl` 非空时，比赛库卡片封面 SHALL 直接以 `<img>` 展示该预生成 poster，不再为封面解码视频流；`thumbnailUrl` 缺失时，SHALL 继续走现有视频流首帧（`coverVideoUrl` / `cameraCoverSources`）与中性占位降级链路。

#### Scenario: poster 命中直接显示
- **WHEN** 卡片 `thumbnailUrl` 非空
- **THEN** 封面 SHALL 以 `<img src=thumbnailUrl>` 全幅 `object-cover` 显示
- **AND** 不应为封面创建 `<video>` 元素或触发视频流解码

#### Scenario: poster 缺失回退视频流
- **WHEN** 卡片 `thumbnailUrl` 为空，但 `coverVideoUrl` 或 `cameraCoverSources` 存在
- **THEN** 封面 SHALL 按现有 `LibraryCover` 逻辑渲染视频流首帧（含双摄左右拼接与「双摄」标识）

#### Scenario: 全缺失中性占位
- **WHEN** `thumbnailUrl`、`coverVideoUrl`、`cameraCoverSources` 均无
- **THEN** 封面 SHALL 显示既有中性占位（球场线纹理 + `Video` 图标），不得伪造画面
