## MODIFIED Requirements

### Requirement: view capability 门控基于 selected Job 的 AnalysisResult manifest

Workspace 结果类 view 的可开性 SHALL 依据 selected Job 状态与 selected Job 的 AnalysisResult artifact manifest 一次判定，而非仅看 primaryAnalysisJobId 是否存在。未显式选择时，selected Job SHALL 回退为 primaryResultAnalysisJobId。初始门控 SHALL NOT 通过逐 view 拉取重产物判断。缺产出的合法 view SHALL 停在原 URL 显示缺产物提示；非法 view SHALL replace 落到 overview。

#### Scenario: selected Job 缺该 view 产出物
- **WHEN** selected Job 存在但未产出球路或报告等特定 artifact
- **THEN** 用户 SHALL 仍停在原 URL
- **AND** 系统 SHALL 显示“该分析版本未生成该数据”类提示
- **AND** SHALL NOT 回退读取 primary Job 或其他 Job 的产物

#### Scenario: selected Job 改变后 capability 重算
- **WHEN** 用户从 Job A 切换到 Job B
- **THEN** 系统 SHALL 按 Job B 状态与 manifest 重算所有结果 view capability
- **AND** SHALL NOT 复用 Job A 的 manifest 或 capability 结果

#### Scenario: 非法 view
- **WHEN** 用户访问当前素材来源根本不支持的 view
- **THEN** 系统 SHALL replace 到 overview
- **AND** 若当前 analysisJob 合法，URL SHALL 保留该选择

#### Scenario: 初始门控不拉重产物
- **WHEN** Workspace 首次判定 selected Job 的各 view 可开性
- **THEN** 系统 SHALL 仅基于 Job 状态与 AnalysisResult manifest 的 artifact metadata 完成
- **AND** SHALL NOT 逐一拉取 trajectory、report、heatmap 或 overlay 等重产物

#### Scenario: 无可用 selected result
- **WHEN** 素材无 completed 结果且未显式选中可诊断的 terminal Job
- **THEN** 结果类 view SHALL 不可用并显示待分析或无结果提示

### Requirement: Job-bound Content 组件使用统一 selected Job

Workspace SHALL 从同一 SelectedAnalysisContext 向数据分析、球路、报告与技术详情 Content 传入 Job ID。素材级视频和片段 Content 不受 selected Job 数据源限制。

#### Scenario: 四个结果 Content 使用同一 Job
- **WHEN** selected Job 为 Job A
- **THEN** Vision、BallTrajectory、Report 和 Technical Content SHALL 全部获得 Job A 作为数据源
- **AND** 任一 Content MUST NOT 内部改回 primaryResultAnalysisJobId

#### Scenario: 快速切换版本不显示过期响应
- **WHEN** 用户在 Job A 的数据请求尚未完成时切换到 Job B
- **THEN** 系统 SHALL 取消或忽略 Job A 的过期响应
- **AND** 页面 SHALL NOT 在 Job B 的选中态下渲染 Job A 内容

#### Scenario: 素材级 view 不被历史结果替换
- **WHEN** 用户已选中历史 Job A 并进入视频或片段 view
- **THEN** 视频与片段 SHALL 继续表达当前 LibraryItem 素材
- **AND** SHALL NOT 将 Job A 误当成另一个素材容器
