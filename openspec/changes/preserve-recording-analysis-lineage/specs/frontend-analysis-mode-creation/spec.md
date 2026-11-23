## ADDED Requirements

### Requirement: 来源错误的 machine code 解析

前端 SHALL 依据响应体中的 machine code 判定来源错误，而不是依据 HTTP 状态码。

系统 MUST 同时接受历史 HTTP 400 与新 HTTP 409 两种状态码携带的同一 machine code（`source_ownership_mismatch`），并进入同一用户提示分支。系统 MUST NOT 把其他普通 400 错误解释为来源冲突；无法识别 code 时 MUST 落入通用错误分支。

前端错误对象 SHALL 暴露结构化的 machine code 与 details，使调用方无需解析拼接后的错误字符串即可分支。

#### Scenario: 历史 400 与新 409 同分支

- **WHEN** 创建分析返回 HTTP 400 且响应体 `code = source_ownership_mismatch`
- **THEN** 前端 SHALL 进入来源冲突提示分支

- **WHEN** 创建分析返回 HTTP 409 且响应体 `code = source_ownership_mismatch`
- **THEN** 前端 SHALL 进入同一提示分支

#### Scenario: 普通 400 不被误判

- **WHEN** 创建分析返回 HTTP 400 且 `code` 为其他值或缺失
- **THEN** 前端 MUST NOT 展示来源冲突文案
- **AND** SHALL 落入通用错误分支

#### Scenario: 结构化错误字段可读取

- **WHEN** 响应体包含 `{code, message, details}`
- **THEN** 前端错误对象 SHALL 提供可读取的 code 与 details
- **AND** MUST NOT 要求调用方解析拼接后的错误文本

#### Scenario: 错误提示可行动

- **WHEN** 来源冲突被展示给用户
- **THEN** 提示 SHALL 说明请求来源与录制不一致
- **AND** SHALL 引导用户从录制页重新发起，而不是只显示状态码
