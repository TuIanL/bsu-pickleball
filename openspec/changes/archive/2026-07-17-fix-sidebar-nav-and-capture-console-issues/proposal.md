## Why

两个已归档 Change 的验收中发现了 7 个问题，涵盖导航映射错误、布局缺陷、时钟显示异常和录制失败缺乏反馈。这些问题阻塞了后续使用，应在继续新功能前修复。

## What Changes

- **侧边栏导航映射修正**: 工作台、视频管理、分析任务三个导航项指向错误的页面路径
- **顶部栏移除**: standard 模式下删除全局 Topbar（首页/任务历史按钮），首页跳转移至侧边栏品牌 Logo
- **录制状态块交互**: 点击整块跳转至对应录制工作台；删除语义错误的「结束录制」按钮
- **时钟显示修正**: 修复 computeElapsedMs 的计时问题
- **重复存储位置删除**: 删除录制工作台中与 Header 重复的「录制保存位置」行
- **控制区布局修正**: 解决 RecordingControlPanel 在 flex 容器中被挤压的问题
- **录制失败状态 UI**: 在 failed/starting 等非录制态下显示诊断信息

## Capabilities

### New Capabilities
（无新能力引入——全部是已有行为的修正）

### Modified Capabilities
（无需求级变更——全部是实现级 bugfix）

## Impact

- **AppSidebar.tsx**: navItems 路径修正；品牌 Logo 增加首页跳转；ActiveRecordingBlock 整块可点击
- **AppShell.tsx**: standard 模式去掉 Topbar；landing 模式保留
- **CaptureConsolePage.tsx**: 删除存储位置行；控制区布局调整；录制失败显示错误信息
- **useActiveCaptureTake.ts**: 时钟计算逻辑修正
