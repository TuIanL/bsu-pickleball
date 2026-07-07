## 1. 后端摄像头预览流

- [x] 1.1 在 `backend/app/camera/` 中新增预览服务模块，封装摄像头 URL 鉴权拼接、`cv2.VideoCapture` 打开、读帧、JPEG 编码和资源释放。
- [x] 1.2 为预览服务实现受控帧率输出，避免按摄像头原始帧率无限制编码。
- [x] 1.3 在 `backend/app/api/routes_camera.py` 增加 `GET /api/cameras/{camera_id}/preview` 端点。
- [x] 1.4 对不存在摄像头返回 404，对无法打开或读帧失败返回稳定错误响应。
- [x] 1.5 确保客户端断开预览连接时停止帧循环并释放 `VideoCapture`。

## 2. 前端预览 URL 与状态

- [x] 2.1 在 `src/services/analysisClient.ts` 增加摄像头预览 URL 构造函数。
- [x] 2.2 在 `CameraHubPage` 中根据 `recordingForm.camera_id` 派生当前选中的摄像头和预览 URL。
- [x] 2.3 在开始录制区域加入实时预览区域，覆盖未选择、加载中、显示画面、加载失败状态。
- [x] 2.4 切换摄像头时更新预览源，并避免继续显示旧摄像头画面。
- [x] 2.5 预览失败时保留探测、录制表单和历史列表可用。

## 3. 录制历史播放

- [x] 3.1 在录制历史中为 `status=completed` 且存在 `video_id` 的 session 显示播放入口。
- [x] 3.2 使用现有 `getVideoStreamUrl(session.video_id)` 构造录制视频播放地址。
- [x] 3.3 实现录制视频播放器视图，可用弹窗或历史列表展开方式展示 `<video controls>`。
- [x] 3.4 支持关闭播放器后回到录制历史上下文。
- [x] 3.5 用户选择另一条可播放录制时切换播放器源，不修改任何录制 session 状态。
- [x] 3.6 对 `recording`、`canceled`、`failed` 或缺少 `video_id` 的记录不显示普通播放入口，并保留状态说明。

## 4. 回放失败与边界状态

- [x] 4.1 为视频流 404 或浏览器播放错误增加前端失败状态。
- [x] 4.2 确认播放器不直接使用或暴露后端本地 `video_path`。
- [x] 4.3 确认已有 completed session 在有 `video_id` 时无需迁移即可播放。

## 5. 验证

- [x] 5.1 运行 TypeScript 构建，确认前端类型和打包通过。
- [x] 5.2 运行 Python 语法检查或相关后端测试，确认新增预览模块和路由可导入。
- [x] 5.3 使用真实或本地可访问摄像头验证预览流能显示当前画面。
- [x] 5.4 使用真实录制流程验证停止录制后历史列表出现播放入口，并能打开播放视频。
- [x] 5.5 验证预览失败、摄像头不存在、缺少 `video_id`、视频文件丢失等异常状态显示稳定。
