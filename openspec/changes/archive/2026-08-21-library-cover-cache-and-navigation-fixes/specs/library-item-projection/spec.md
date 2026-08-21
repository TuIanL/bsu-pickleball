## ADDED Requirements

### Requirement: 双摄封面机位流地址

`sync_recording` 的展示元数据 SHALL 暴露两路机位流地址（`cam_1`/`cam_2`），供双摄封面左右拼接渲染；`coverVideoUrl` 作为兼容字段保留。

#### Scenario: 双摄投影暴露机位流
- **WHEN** `libraryAdapter` 投影一个 `sync_recording` LibraryItem 且 `registered_video_ids.cam_1/cam_2` 存在
- **THEN** ViewModel SHALL 携带 `cameraCoverSources: { cam_1?: string; cam_2?: string }`，其值由 `getVideoStreamUrl()` 构建
- **AND** `buildLibraryItems` 与 `resolveLibraryItemByRef` 两处 SHALL 保持一致

#### Scenario: 机位流缺失
- **WHEN** 某一路（或两路）`registered_video_ids` 不存在
- **THEN** 对应字段 SHALL 省略（undefined），由封面渲染层据此做占位/退让，而非伪造