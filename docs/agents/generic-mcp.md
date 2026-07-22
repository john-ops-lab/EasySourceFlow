# 其他 MCP 客户端

只要 Agent 能启动本地 stdio MCP 服务，就可以使用 EasySourceFlow 的核心能力。

## MCP 配置

```json
{
  "mcpServers": {
    "easysourceflow": {
      "command": "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp",
      "env": {
        "EASYSOURCEFLOW_BASE_URL": "http://127.0.0.1:8765"
      }
    }
  }
}
```

不同客户端可能使用 `mcp_servers`、`servers` 或自己的设置界面，不能直接假设上述 JSON 字段名适用。请把 command、env 和 stdio transport 对应到客户端的官方配置格式。

## Skill 和附件

如果客户端支持 Agent Skills 标准，把 `skills/easysourceflow/` 安装到其官方 Skill 目录。否则把[通用调用契约](../AGENT_INTEGRATION.md#3-通用调用契约)加入客户端规则。

需要提交附件时，在 MCP 进程环境中配置：

```text
EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS=<CLIENT_UPLOAD_DIR>
```

只允许客户端实际保存用户附件的最小目录，不要允许整个主目录或文件系统。

## 验收

1. 连接 MCP 后确认能列出 EasySourceFlow 工具。
2. 调用 `easysourceflow_health`。
3. 提交文章并轮询到成功。
4. 确认客户端原样交付 `result.summary_markdown`。

无法启动本地 stdio MCP 的纯云端 Agent 不能直接接入本机服务，可继续使用 EasySourceFlow Web。
