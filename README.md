# Browser Node Watchdog

这是 `ai-compare-server` 旧版配套的 Windows 本地巡检脚本。

它只处理高频、低风险场景：节点超过 30 分钟未上报时，在 CPU 和内存允许的情况下，对配置中的 BitBrowser 或 Donut Browser profile 执行一次普通重启，并通过新的插件上报时间判断是否恢复。

它不会自动处理应用崩溃弹窗、代理切换、Tab 清理、AI 账号登录和地区动态扩缩容。

## 运行环境

- Windows 10/11 或 Windows Server；
- Python 3.11 及以上；
- 推荐使用 `uv`；
- BitBrowser 本地 API 已开启；
- Donut 使用 REST API，或 Donut 主窗口保持打开以供 UIA 操作。

## 安装

```powershell
cd C:\Project\tec-do-pro\browser-node-watchdog
Copy-Item config.example.yaml config.yaml
uv sync
```

在当前 PowerShell 会话设置中央服务 Token：

```powershell
$env:AI_COMPARE_PANEL_TOKEN="与服务端 PANEL_API_TOKEN 一致的值"
```

如果使用 Donut REST API：

```powershell
$env:DONUT_API_KEY="Donut 本地 API Token"
```

不要把 Token 写入 `config.yaml`。

## 配置实例

最稳妥的配置方式是明确列出本机需要自动管理的 profile：

```yaml
instances:
  - browser_name: "AU-DT-HK3-17"
    browser_type: "bitbrowser"
    profile_id: "BitBrowser真实profile ID"
    auto_restart: true
    priority: 10

  - browser_name: "US-DT-HK3-01"
    browser_type: "donut"
    profile_name: "124"
    auto_restart: true
    priority: 20
```

`browser_name` 必须与插件上报给 `ai-compare-server` 的名称完全一致。

## 自动发现

先在 `config.yaml` 中配置中央服务和启用的浏览器管理器，然后运行：

```powershell
uv run python watchdog.py --config config.yaml --discover
```

脚本生成：

```text
config.discovered.yaml
```

规则：

- 本地 profile 名称与中央 `browserName` 完全一致时自动匹配；
- 无法准确匹配的 profile 会设置 `auto_restart: false`；
- 原配置中已经确认的 profile 映射会保留；
- 必须人工检查生成结果，再将确认后的内容合并到 `config.yaml`。

自动发现不会启动或停止任何浏览器。

## 先执行一次

上线前先运行单次巡检：

```powershell
uv run python watchdog.py --config config.yaml --once --verbose
```

日志位于：

```text
logs\watchdog.log
```

## 持续运行

```powershell
uv run python watchdog.py --config config.yaml
```

控制台关闭后脚本也会停止。人工验证稳定后，再配置 Windows 任务计划程序。

Donut 使用 `uia` 模式时，任务必须选择“仅当用户登录时运行”，并保持 Donut 主窗口所在的桌面会话可用。

## 处理结果

日志中的常见结果：

| 结果/原因 | 含义 |
|---|---|
| `RECOVERED` | 重启后服务端收到新心跳 |
| `node_missing` | 配置的节点在中央状态中不存在，需要人工核对 |
| `banned` | 节点已被后台禁用，不自动重启 |
| `high_cpu` | CPU 达到限制，本轮不启动 |
| `high_memory_percent` | 内存使用率达到限制，本轮不启动 |
| `low_available_memory` | 可用内存不足，本轮不启动 |
| `restart_cooldown` | 最近已尝试重启，不重复操作 |
| `restart_failed` | 本地浏览器控制失败，需要人工处理 |
| `heartbeat_not_restored` | 浏览器启动后仍无新心跳，检查代理或插件 |
| `central_unavailable` | 中央服务异常，本轮不操作任何浏览器 |

## 安全边界

- 每轮默认最多重启一个实例；
- 不会启动配置之外的 profile；
- 不会自动删除 profile；
- 不会自动结束浏览器管理器或 Chromium 子进程；
- 不会在 CPU、内存超过阈值时启动浏览器；
- 普通重启失败后不会在同一轮再次重试；
- 中央服务不可用时不会根据旧状态重启浏览器。

## 测试

```powershell
uv run pytest
```
