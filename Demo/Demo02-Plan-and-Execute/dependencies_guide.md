# code_agent.py 完整导入列表

> 源文件：`MokioAgent/src/mokioclaw/agents/code_agent.py`

---

## 一、标准库（Python 内置，无需安装）

```python
import json
from typing import Any, Callable
```

---

## 二、langchain_core（第三方，需 pip install）

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
```

---

## 三、mokioclaw 本地模块（项目内部）

```python
from mokioclaw.core.state import RuntimeState
from mokioclaw.graph.memory import build_layered_memory, format_layered_memory_for_prompt, memory_event
from mokioclaw.graph.state import MokioGraphState
from mokioclaw.prompts.stage3 import CODE_AGENT_PROMPT
from mokioclaw.providers.openai_provider import create_model
from mokioclaw.tools import build_tools
from mokioclaw.tools.todo_tool import persist_todos, update_todo
```

---

## 四、一键安装所有第三方依赖

```bash
pip install langchain-core langchain-openai langgraph
```

> 如果使用 uv：
> ```bash
> uv add langchain-core langchain-openai langgraph
> ```

---

## 五、完整导入代码块（可直接复制）

```python
from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from mokioclaw.core.state import RuntimeState
from mokioclaw.graph.memory import build_layered_memory, format_layered_memory_for_prompt, memory_event
from mokioclaw.graph.state import MokioGraphState
from mokioclaw.prompts.stage3 import CODE_AGENT_PROMPT
from mokioclaw.providers.openai_provider import create_model
from mokioclaw.tools import build_tools
from mokioclaw.tools.todo_tool import persist_todos, update_todo
```
