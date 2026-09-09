## ADDED Requirements

### Requirement: 历史迁移与运行期读取分离

系统 MUST 在启动迁移边界或显式重导命令导入历史 JSON；JobStore.get/list 与取消检查 SHALL 不扫描历史目录、不执行迁移、不刷新兼容文件。状态实际变更后 SHALL 继续维护所需快照。

#### Scenario: 热路径操作数恒定
- **WHEN** 分别存在 1、100、1000 个历史任务且重复查询同一任务或检查取消
- **THEN** 每次查询 SHALL 只访问所需控制面记录，历史扫描/JSON read/write 次数均为零，数据库操作数 SHALL 不随历史任务数增长

#### Scenario: 启动与重复迁移
- **WHEN** 首次启动或显式重导历史 JSON，或 API/Worker 同时启动
- **THEN** 导入 SHALL 幂等且不覆盖已有控制面任务，完成标记 SHALL 持久化，坏文件 SHALL 被记录并跳过

#### Scenario: 完成迁移后新增历史文件
- **WHEN** 导入完成后旧目录新增 JSON
- **THEN** 普通查询 SHALL 不自动发现，显式重导 SHALL 能安全导入缺失记录

#### Scenario: 跨进程取消仍可见
- **WHEN** API 提交取消且 Worker 在下一个既有安全检查点查询
- **THEN** Worker SHALL 读取新取消状态并遵循原取消/终态/lease 规则，不依赖长期内存缓存
