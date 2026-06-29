# StructuredTool + bind_tools 学习笔记

**时间：** 2026-06-29 16:05

---

## 一、核心概念

### 1. `StructuredTool` 是什么？

```
StructuredTool = 普通 Python 函数 + 给 LLM 看的"说明书"
```

| 组成部分 | 是什么 | 给谁看 |
|---------|--------|--------|
| `func=add` | 真正执行的 Python 代码 | Python 解释器 |
| `name="Add"` | 工具的唯一标识 | LLM |
| `description="做加法运算"` | **最重要！** 告诉 LLM 这个工具什么时候用、做什么用 | ⭐ **给 LLM 看，LLM 靠它决策** |

### 2. `.bind_tools(tools)` 是什么？

```python
model_with_tools = model.bind_tools(tools)
```

**这就是"给 LLM 装工具箱"的官方写法**，作用：
- 把工具列表自动转成 OpenAI 能理解的 JSON Schema 格式
- 把 Schema 拼到 System Prompt 里传给 LLM
- 让 LLM 知道"我有这些工具可以用"

---

## 二、完整的 Tool 调用闭环

```mermaid
flowchart LR
    A[用户提问：123 × 456?] -->|传入| B[LLM，已 bind_tools]
    B -->|LLM 看了工具描述，自主决策| C[返回 tool call]
    C -->|包含| D{name: "Multiply", args: {a:123, b:456}}
    
    D -->|Python 代码调用| E[tool.invoke(args)]
    E -->|执行| F[返回结果 56088]
    
    F -->|包装成| G[ToolMessage]
    G -->|加回 messages，传给 LLM| B
    
    style B fill:#4CAF50,color:white
    style E fill:#FF9800,color:white
```

---

## 三、关键知识点汇总

### ✅ 谁决定调用什么工具？

**LLM 自己决定！**
- 参数名（`a`、`b`）是 Python 函数签名决定的
- 参数值（`123`、`456`）是 **AI 自己根据问题推断出来的**

### ✅ 为什么要包装成 ToolMessage？

因为 LLM 需要看到"工具执行结果"才能做下一步决策。ToolMessage 就是：
> ✅ 你刚才调用的 Multiply 工具，执行结果是 56088

---

## 四、对应到 MokioAgent 源码

| 知识点 | 源码位置 |
|--------|---------|
| planner 构建工具集 | [nodes.py#L473-L495](file:///c:/EngineeringProjects/SiHuiFuRan-Agent/MokioAgent/src/mokioclaw/graph/nodes.py#L473-L495) |
| 执行工具调用 | [nodes.py#L575-L594](file:///c:/EngineeringProjects/SiHuiFuRan-Agent/MokioAgent/src/mokioclaw/graph/nodes.py#L575-L594) |
| 委派 searchAgent | [nodes.py#L536-L555](file:///c:/EngineeringProjects/SiHuiFuRan-Agent/MokioAgent/src/mokioclaw/graph/nodes.py#L536-L555) |
| 委派 codeAgent | [nodes.py#L558-L572](file:///c:/EngineeringProjects/SiHuiFuRan-Agent/MokioAgent/src/mokioclaw/graph/nodes.py#L558-L572) |

**架构设计思想：**
- **planner 是 supervisor（管理者）** — 只做决策，不亲自干活
- **searchAgent / codeAgent 是 specialist（专家）** — 被 planner 调用，实际干活
- **两者之间靠 StructuredTool + ToolMessage 沟通**

---

## 五、最小记忆点

```
1. StructuredTool.from_function()  # 把Python函数包成工具
2. model.bind_tools(tools)         # 把工具装给LLM
3. LLM 自主返回 tool_calls        # LLM 决定调用什么、传什么参数
4. tool.invoke(args)               # Python 真正执行
5. 包装成 ToolMessage 还给 LLM     # 形成闭环
```
