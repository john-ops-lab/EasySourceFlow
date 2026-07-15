# ADR 0001: 使用 MCP 作为 Agent 集成入口

## 状态

Accepted

## 背景

用户希望 Codex、OpenClaw 和其他 Agent 都能调用本地总结能力。可选方式包括：

- 每个 Agent 各自写插件。
- 暴露 HTTP API，让 Agent 自行调用。
- 使用 shell 命令。
- 使用 MCP。

## 决策

使用 MCP 作为 Agent 集成入口。项目提供 `easysourceflow_mcp`，对外暴露少量高层工具。

## 理由

- MCP 是 Agent 工具集成的通用协议。
- 工具 schema 可以描述输入、输出和行为。
- stdio transport 适合本机单用户部署。
- 后续可以增加 streamable HTTP，不影响核心业务。
- 统一入口可以限制权限，避免 Agent 直接操作底层工具。

## 替代方案

### 直接 HTTP API

优点：

- 简单。
- 易测试。

缺点：

- Agent 集成需要额外 glue code。
- 缺少标准工具发现能力。

### shell 命令

优点：

- 最快实现。

缺点：

- 参数校验弱。
- 错误结构差。
- 长任务和状态查询不自然。

### 多个第三方 MCP 拼装

优点：

- 复用现成项目。

缺点：

- Agent 需要自己编排流程。
- 更容易让 Agent 误串流程或误写文件。
- 权限边界分散。

## 后果

- 需要实现 MCP 适配器。
- 需要维护工具 schema。
- 需要为不同 Agent 写配置说明。
- 换来更清晰的 Agent 调用边界和更好的长期扩展性。
