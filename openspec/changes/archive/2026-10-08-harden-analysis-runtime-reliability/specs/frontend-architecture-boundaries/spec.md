## MODIFIED Requirements

### Requirement: 路由解析必须显式处理 pathname 和 search
前端 SHALL 使用同时接收 `pathname` 和 `search` 的解析入口处理浏览器初始加载、前进后退和内部导航，避免 query string 在刷新时丢失。查询参数取值 SHALL 经解析入口或受控订阅获取，SHALL NOT 由页面在渲染期直接读取浏览器当前位置对象；查询参数赋给判别联合类型前 SHALL 校验其属于受支持字面量集合。

#### Scenario: 刷新 upload query 路由
- **WHEN** 浏览器在 `/upload?videoId=video-1&source=recording` 初始加载
- **THEN** 路由解析 SHALL 使用 `pathname = "/upload"` 和 `search = "?videoId=video-1&source=recording"` 生成 upload RouteState
- **AND** RouteState SHALL 包含 `videoId = "video-1"` 和 `source = "recording"`

#### Scenario: popstate 保留 query 解析
- **WHEN** 用户通过浏览器前进或后退回到带 query string 的 upload 路由
- **THEN** popstate handler SHALL 使用当前 `window.location.pathname` 和 `window.location.search` 更新 RouteState

#### Scenario: 内部导航统一解析 query
- **WHEN** 应用内部调用 navigate 并传入 `/upload?videoId=video-1&source=recording`
- **THEN** navigate SHALL 通过 pathname 和 search 解析 RouteState
- **AND** RouteState SHALL 与刷新同一路径时一致

#### Scenario: 页面不在渲染期读取浏览器当前位置

- **WHEN** 开发者查看任一页面组件的渲染函数体
- **THEN** 页面 MUST NOT 在渲染期读取浏览器当前位置对象来获取查询参数
- **AND** 查询参数 SHALL 来自路由状态、props 或受控的订阅状态
- **AND** 浏览器当前位置对象 SHALL 仅在事件回调、初始化函数或订阅建立处读取

#### Scenario: 查询参数取值校验后才赋给判别联合

- **WHEN** 某查询参数被赋给 `cam_1` / `cam_2` 之类的判别联合类型
- **THEN** 系统 SHALL 先校验该取值属于受支持字面量集合
- **AND** 不属于集合的取值 SHALL 安全回退，MUST NOT 通过类型断言直接当作联合类型成员向下传递
- **AND** MUST NOT 因此产生破损 RouteState 或未定义分支行为

#### Scenario: 路由上下文变化驱动重新渲染

- **WHEN** 用户前进或后退到查询参数不同的同一路径
- **THEN** 依赖查询参数的页面 SHALL 随之重新渲染并展示新参数对应内容
- **AND** 该行为 MUST NOT 依赖页面自身的轮询或定时器副作用

## ADDED Requirements

### Requirement: 轮询 effect 的依赖不得包含每次渲染新建的对象

页面级轮询 effect SHALL 只依赖标量信号（如来源枚举、目标 id、是否活跃、加载标志），MUST NOT 直接依赖每次请求都返回新引用的数组或对象。轮询 SHALL 具备在途请求守卫，并 SHALL 在页面隐藏时暂停、恢复可见时补一次对账。

#### Scenario: 依赖数组不含请求结果对象

- **WHEN** 开发者查看带轮询的页面 effect 依赖数组
- **THEN** 依赖数组 SHALL 只包含标量值
- **AND** MUST NOT 包含每次请求都返回新引用的列表或会话对象

#### Scenario: 轮询定时器不因无关渲染反复重建

- **WHEN** 轮询所在的 effect 依赖的标量信号未变化而组件发生其他原因的重渲染
- **THEN** 轮询定时器 MUST NOT 被清除并重建
- **AND** 重建导致的轮询空档 MUST NOT 出现

#### Scenario: 单次请求慢于轮询间隔

- **WHEN** 某次轮询请求耗时超过轮询间隔
- **THEN** 系统 MUST NOT 叠加并发轮询请求
- **AND** SHALL 在前一请求完成后继续轮询

#### Scenario: 页面隐藏时暂停轮询

- **WHEN** `document.hidden` 为 true
- **THEN** 轮询 SHALL 停止发起新请求

#### Scenario: 页面恢复可见后补一次对账

- **WHEN** 页面从隐藏恢复可见且轮询条件仍成立
- **THEN** 系统 SHALL 立即发起一次对账请求

#### Scenario: 轮询结果使用最新请求上下文

- **WHEN** 轮询回调需要读取当前列表或会话上下文
- **THEN** 系统 SHALL 读取最新上下文而非 effect 启动时的过期快照
- **AND** MUST NOT 把过期对象写入状态

### Requirement: 图表封装的 init effect 不得依赖事件绑定对象

图表封装 SHALL 把实例初始化生命周期与图表事件绑定生命周期分离：事件绑定对象 MUST NOT 进入实例 init effect 的依赖数组。图表 option 与事件绑定对象若需引用稳定，调用方 SHALL 通过记忆化保持稳定引用。

#### Scenario: 事件绑定不触发实例重建

- **WHEN** 调用方以非稳定引用的对象字面量传入事件绑定
- **THEN** 组件重渲染 MUST NOT 导致图表实例被 dispose 并重新初始化
- **AND** 用户已完成的缩放、平移与视口状态 SHALL 保持不变

#### Scenario: 重建期不产生空白闪烁

- **WHEN** 图表实例确实需要重建（如主题切换或 option 实质变化）
- **THEN** 重建过程 MUST NOT 向用户呈现可见的空白帧
- **AND** 容器 SHALL 保持既有高度以避免布局跳动

#### Scenario: 事件在重建后仍生效

- **WHEN** 图表实例因 option 或主题变化被重建
- **THEN** 事件绑定 SHALL 在新实例上重新生效
- **AND** 旧实例上的绑定 SHALL 被移除，MUST NOT 遗留未释放的实例或监听

#### Scenario: 相同 option 引用不触发重建

- **WHEN** 组件重渲染但记忆化的 option 与主题均未变化
- **THEN** 系统 MUST NOT 重新初始化图表实例