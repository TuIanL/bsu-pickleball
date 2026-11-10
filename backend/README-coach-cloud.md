# Render 教学助教 API

入口 `app.coach_cloud:app` 仅开放教学模型调用和健康检查，复用现有三个 Agent 工具。
完整视频推理、本地文件、相机与管理 API 不在这个服务中。

Render Web Service 配置：

- Branch: `demo/ai-race-education-coach`
- Root Directory: `backend`
- Build Command: `pip install -r requirements-coach-cloud.txt`
- Start Command: `uvicorn app.coach_cloud:app --host 0.0.0.0 --port $PORT --workers 1`
- Health Check: `/healthz`
- Environment: `PICKLEBALL_COACH_AGENT_API_KEY`、`PICKLEBALL_COACH_AGENT_BASE_URL`、`PICKLEBALL_COACH_AGENT_MODEL`、`COACH_ALLOWED_ORIGINS`

密钥只保存在服务端环境变量中，禁止提交 `.env` 或设置成 `VITE_*` 变量。
`COACH_ALLOWED_ORIGINS` 是允许使用此接口的前端完整来源地址，多个地址用英文逗号分隔，不带末尾斜杠。

前端 Static Site 构建变量：

- `VITE_COACH_AGENT_MODE=live`
- `VITE_COACH_API_URL=https://<教学服务>.onrender.com`

前端变量修改后必须重新构建部署。访问 `/reports/performance`，保持“模型”模式，提交问题确认实时回复及工具执行。
演示报告仍标注样例数据；在线模型接通不代表已经上传真实分析报告。

公开体验版限制：单次请求 32 KiB、问题 2000 字、最多 6 条历史记录；每个客户端每小时 30 轮，全实例滚动 24 小时 300 轮，同时最多 2 轮。
限额仅用于单进程演示，保存在内存中，实例重启会清空；不能替代面向大规模用户的账户认证与计费系统。
