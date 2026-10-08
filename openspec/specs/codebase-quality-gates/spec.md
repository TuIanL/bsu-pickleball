# codebase-quality-gates Specification

## Purpose

定义前后端质量门禁命令的可通过条件，并把后端测试与本地运行数据隔离。

同时规范 Ruff、活跃 OpenSpec 变更、异常处理理由与运行时环境变量的检查范围，使执行结果可以作为可重复的交付证据。

## Requirements
### Requirement: 前端质量命令可通过

系统 SHALL 保持前端 TypeScript 构建、测试和 Lint 命令可重复执行并通过。

#### Scenario: 前端构建通过

- **WHEN** 在仓库根目录执行 `npm run build`
- **THEN** TypeScript 编译和 Vite production build SHALL 成功退出
- **AND** 不得通过关闭 `strict` 或隐藏类型错误来达成通过

#### Scenario: 前端测试通过

- **WHEN** 执行 `npm test`
- **THEN** 所有现有前端测试 SHALL 通过
- **AND** 路由、录制分析桥接、artifact 状态和降级行为 SHALL 有对应回归测试

#### Scenario: 前端 Lint 通过

- **WHEN** 执行 `npm run lint`
- **THEN** ESLint SHALL 无 error 退出
- **AND** 任何保留 warning SHALL 有局部规则说明，不得通过全局关闭 React hooks 或 TypeScript 规则隐藏问题

### Requirement: 后端测试与本地运行数据隔离

后端测试 SHALL 使用测试专用的临时数据库、存储目录和模型目录，不得依赖仓库默认 `backend/data` 或真实模型资产。

#### Scenario: 录制生命周期测试在空数据库运行

- **WHEN** 单独或全量执行录制生命周期测试
- **THEN** 测试 SHALL 不受默认 SQLite 中历史 `CaptureTake` 记录影响
- **AND** fake session factory 对活跃录制查询 SHALL 返回显式可控的结果

#### Scenario: 模型自动发现测试显式控制资产

- **WHEN** 测试验证模型未配置或模型自动发现
- **THEN** 测试 SHALL 通过临时模型目录显式创建或省略模型文件
- **AND** 结果 SHALL 不随仓库 `models/` 目录当前内容变化

#### Scenario: 测试运行不产生工作区污染

- **WHEN** 执行后端测试
- **THEN** 测试产物 SHALL 写入 pytest 临时目录或明确的测试输出目录
- **AND** 不得改变默认运行数据库中的业务记录

### Requirement: 后端质量命令可通过

系统 SHALL 将后端 pytest 全量通过作为实现完成的必要条件。

CI SHALL 实际执行仓库已配置的 Python 静态检查（`ruff`），并对死变量（未使用的局部赋值）与未使用导入这两类规则设为阻断。已配置但未被任何门禁执行的检查项 SHALL 视为门禁失效。

达成通过 MUST NOT 依靠关闭规则、扩大忽略清单或降低规则严重级别。若某条规则确有不可消除的误报，MUST 在忽略配置中附带有理由的、范围最小的局部豁免，SHALL NOT 通过整体关闭该规则来让门禁变绿。

#### Scenario: 后端测试通过
- **WHEN** 在 `backend` 目录执行 `python -m pytest -q`
- **THEN** 所有测试 SHALL 通过
- **AND** 失败必须能定位到具体 API、服务或视觉模块，不得由共享历史状态造成随机失败

#### Scenario: CI 实际执行已配置的静态检查

- **WHEN** CI 在后端质量门禁步骤运行
- **THEN** 它 SHALL 执行仓库已配置的 Python 静态检查命令
- **AND** 该命令的规则集 SHALL 与仓库配置一致
- **AND** MUST NOT 出现「配置已声明但门禁从未执行」的状态

#### Scenario: 死变量与未使用导入阻断

- **WHEN** 提交的代码引入了未使用的局部赋值或未使用的导入
- **THEN** CI SHALL 判定门禁失败
- **AND** 该失败 MUST NOT 被自动忽略或降级为警告

#### Scenario: 不通过关闭规则达成通过

- **WHEN** 某条静态检查规则在仓库中触发
- **THEN** 修复方式 SHALL 是修改代码或添加带理由的最小范围局部豁免
- **AND** MUST NOT 通过整体关闭该规则、扩大全局忽略范围或降低严重级别来让门禁通过
- **AND** 门禁配置的任何豁免 SHALL 有可读的理由说明

#### Scenario: 新增豁免需带原因

- **WHEN** 静态检查配置中新增或修改了一条忽略/豁免规则
- **THEN** 该豁免 SHALL 附带说明为何该处不需要这条检查
- **AND** 豁免范围 SHALL 限定在最小必要范围内

### Requirement: 规格门禁必须校验活跃变更

CI SHALL 对 OpenSpec 规格执行严格校验，且校验目标 MUST 是当前活跃的 change。校验 MUST NOT 指向已归档的 change。校验目标 SHALL 由「全部活跃 change」推导或显式列出当前活跃 change，MUST NOT 硬编码单个 change 名称。

当不存在任何活跃 change 时，校验 SHALL 明确通过或明确跳过，MUST NOT 静默地校验一个归档对象并报告成功。门禁 SHALL 能区分「校验通过」与「实际未校验任何规格」。

#### Scenario: 校验目标为活跃 change

- **WHEN** CI 执行 OpenSpec 严格校验
- **THEN** 校验目标 SHALL 是当前活跃的 change
- **AND** MUST NOT 是已归档的 change

#### Scenario: 归档后校验目标不失效

- **WHEN** 某个曾被硬编码在校验命令中的 change 被归档
- **THEN** 校验命令 SHALL 仍然校验当前活跃的 change
- **AND** MUST NOT 退化为校验归档目录中的对象

#### Scenario: 多个活跃 change 都被校验

- **WHEN** 仓库同时存在多个活跃 change
- **THEN** 校验 SHALL 覆盖全部活跃 change
- **AND** 每个 change 的规格错误 SHALL 导致门禁失败

#### Scenario: 校验覆盖 delta 与主规格

- **WHEN** 某个活跃 change 包含对既有能力的 delta 规格
- **THEN** 严格校验 SHALL 覆盖该 delta 的结构与需求格式
- **AND** 需求标题 MUST 能与主规格中的既有需求对应

#### Scenario: 不得静默跳过

- **WHEN** 校验命令未能校验到任何规格
- **THEN** 门禁 SHALL 明确表达「未覆盖」或失败
- **AND** MUST NOT 报告为规格门禁已通过

### Requirement: 静默吞异常必须显式声明理由

后端代码中捕获异常后仅 `pass` / `continue` / `return` 的位置 SHALL 附带机器可读的理由声明，说明为何可以安全忽略该异常。缺少理由声明的静默吞异常 SHALL 视为门禁失败。理由声明 SHALL 说明该处为何不需要额外处理，SHALL NOT 仅作为形式化占位。

#### Scenario: 静默吞异常被声明

- **WHEN** 代码中存在捕获异常后不做任何处理的分支
- **THEN** 该分支 SHALL 附带理由声明
- **AND** 声明 SHALL 说明忽略该异常的具体原因

#### Scenario: 缺少理由声明被门禁拦下

- **WHEN** 提交的代码新增了一个无理由声明的静默吞异常分支
- **THEN** 门禁 SHALL 失败
- **AND** 该失败 MUST NOT 通过补充空字符串理由绕过

#### Scenario: 不得用声明掩盖真实问题

- **WHEN** 某处静默吞异常实际掩盖了一个应当上报或抛出的问题
- **THEN** 理由声明 MUST NOT 用于把该问题合理化
- **AND** 该处 SHALL 按实际语义处理异常（上报、转换或抛出）

### Requirement: 运行时目录环境变量必须贯通到后端进程

启动脚本使用的运行时目录环境变量 SHALL 显式导出给后端进程，使依赖该变量的接口能读到真实值。当该变量缺失时，依赖它的接口 SHALL 返回明确的不可用原因，MUST NOT 返回与「没有匹配日志」无法区分的结果。

#### Scenario: 日志接口在变量已导出时返回匹配行

- **WHEN** 启动脚本已把运行时目录导出给后端进程，且存在该任务的运行日志
- **THEN** 日志读取接口 SHALL 返回匹配到该任务的日志行
- **AND** MUST NOT 返回「无匹配」

#### Scenario: 变量缺失时给出可区分的原因

- **WHEN** 后端进程未获得运行时目录变量
- **THEN** 日志读取接口 SHALL 返回「运行时目录未配置」这一明确原因
- **AND** 该原因 MUST NOT 与「运行日志中无匹配该任务的行」混淆
