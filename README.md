# AgentTrustBench MVP

一个可运行的 Agent 可靠性测试原型。它把 **Worker 单独执行** 和 **Worker 接收 ATB 监督反馈后执行** 放在同一批可重置场景中比较，并保留工具回执、状态变化和验证证据。

## 当前实现

- 12 个任务模板 × 3 个变体：检索、状态修改、政策、失败恢复。
- 进程内合成环境，提供检索、读取、创建、更新和申请审批等工具。
- 确定性验证：最终记录状态、必要工具证据、结构化事实声明、政策违规、步骤预算。
- 执行前与结束前监督：返回 `allow`、`revise` 或 `block`，连同原因和证据。Agent 可据此修正。
- 参考 Agent 与 9 类故障 Agent，用来检查 benchmark 自身能否识别预设错误。
- JSON 轨迹、初始和最终状态哈希，以及一条对照实验命令。

## 运行

要求 Python 3.11+，无运行时第三方依赖。在本目录执行：

```bash
python3 -m atb list
python3 -m atb validate
python3 -m atb compare
python3 -m atb run 06 1 --fault --assisted
python3 -m unittest discover -s tests -v
```

`validate` 要求 36 个参考场景在无监督和有监督下全部通过、监督无误报，且 27 个故障变体全部被发现。`compare` 展示脚本化故障 Agent 在有无反馈时的差异。这些脚本 Agent 只用于验证测试协议，**结果不代表真实模型能力或 ATB 的实际提升幅度**。

## 接入自己的 Agent

有两种接入方式：在 Python 中实现 `next_action(task, history, feedback)`；或运行一个读 stdin JSON、写 stdout JSON 的独立命令。`task` 只包含公开的任务 ID 和用户请求；隐藏断言和初始状态不会传给 Agent。`history` 包含每次工具调用及回执，`feedback` 是 ATB 上一次的监督决定。默认最多返回一次监督反馈。

```python
from atb import FinalResponse, ToolCall, build_scenario, run

class MyAgent:
    def next_action(self, task, history, feedback):
        # 在这里调用你的模型，并将其下一步转换成 ToolCall / FinalResponse。
        # 这是接口示意；实际实现需要管理模型对话与工具 schema。
        return FinalResponse("refused", "示例")

scenario = build_scenario("08", 1)
result = run(scenario, MyAgent(), assisted=True)
print(result["evaluation"])
```

完整工具调用格式见 `atb/agents.py`，可用工具见 `atb/core.py` 的 `Sandbox.execute`。Runner 对每个场景创建新环境；请对每次运行创建新的 Agent 实例。

独立命令的输入形如 `{"task": {...}, "history": [...], "feedback": null, "tools": {...}}`。每次调用只输出一个 JSON 对象：

```json
{"type":"tool","name":"get_record","args":{"record_id":"t05v1_target"}}
```

或者：

```json
{"type":"final","status":"completed","message":"已核实。","claims":[{"record_id":"t05v1_target","field":"status","value":"open","evidence_call_id":"call_1"}]}
```

运行示例：`python3 -m atb run 05 1 --assisted --agent-command "python3 my_worker.py"`。命令在每一步重新启动，Worker 可通过完整 `history` 恢复上下文。请勿把密钥放在命令行参数里。

## 设计边界

本版的监督规则使用场景公开意图和已观察到的状态，验证器另外使用冻结的期望断言。监督层不会读取隐藏断言。脚本化参考 Agent 是特例：它在构建时读取完整场景，只负责验证任务可解和验证器有效。

当前尚未接入模型服务、生产系统、实际 token/费用账单或人工评分。`tokens` 和 `cost_usd` 明确返回 `null`。自然语言回复只做结构化状态与事实声明检查；语气、完整语义和跨领域迁移能力仍需另外评估。环境是进程内模拟，不能被视为生产权限网关。

## 下一阶段的门槛

1. 接入至少一个真实 Worker Agent；同一任务重复运行并记录模型版本与使用量。
2. 盲测一批独立编写的失败轨迹，测监督误报和漏报；不要只使用当前故障脚本。
3. 将任务定义与业务数据生成器分开，增加一个独立领域以测试规则能否复用。
