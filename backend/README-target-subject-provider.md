# 科研人物候选导出

本工具读取受控CFR片段并导出可复核候选，独立于Web/API、产品人物确认、动作标签及数据库。候选第一名不代表人工确认，合成测试通过也不代表真实模型准确率。

## 安装与调用

Python基线为3.11。仓库安装复用统一哈希锁：

```bash
python -m pip install --require-hashes -r backend/requirements-py311.lock
python -m pip install --no-deps -e 'backend[dev]'
```

模型推理环境另外安装vision可选依赖并明确提供本地权重；工具不会因本回归测试下载模型。安装wheel时契约JSON已包含在包内，不要求保留仓库目录。

```bash
target-subject-provider --request request.json --output new-result.json
```

输入Schema/示例见 `contracts/target_subject/v1`。pilot/formal要求干净代码；输入文件及模型摘要写入来源信息。输出必须是新文件。

## 输入与失败边界

实际宽高必须与请求一致；fps必须有效并匹配请求，容差为相对0.001、绝对0.01，仅容忍元数据浮点误差。完整解码后实际帧数必须完全等于声明值，多/少、提前结束、逐帧尺寸异常均拒绝导出，不截断候选或补尾帧，失败不写结果。单帧检测异常保留error记录，不冒充检测成功。

本工具使用CFR源帧/fps，不支持以名义fps替代VFR的真实PTS，也不代替平台双摄时间合同。

## 可复现配置

`configuration.tracker_algorithm`可选`motion`或`legacy`，省略时固定`motion`，忽略`PICKLEBALL_TRACKER_ALGORITHM`环境变量。有效配置摘要包含解析后的算法默认值；省略与显式motion等价，显式legacy产生不同摘要。模型路径在配置摘要中使用逻辑引用，实际内容身份单独由SHA-256保存。

## 回归与分发检查

```bash
cd backend
python -m pytest -q tests/test_target_subject_contract.py tests/test_target_subject_provider.py tests/test_target_subject_distribution.py tests/test_multi_object_tracker.py
```

分发测试在临时目录构建sdist，再离线构建wheel并从独立目录加载全部Schema、样本和CLI；不会写原数据、加载真实模型或使用产品数据库。契约同步规则见公开目录README。
