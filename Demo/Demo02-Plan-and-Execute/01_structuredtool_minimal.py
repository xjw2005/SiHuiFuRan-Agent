"""
StructuredTool 最小可运行示范

核心概念：
StructuredTool = 普通 Python 函数 + "LLM 能看懂的说明书"
"""
from langchain_core.tools import StructuredTool


# ─── 1. 先写一个普通的 Python 函数 ──────────────────
def add(a: int, b: int) -> int:
    """两个数相加"""
    return a + b


# ─── 2. 用 StructuredTool 包装成 LLM 能用的工具 ─────
calculator = StructuredTool.from_function(
    func=add,                      # 真正执行的 Python 函数
    name="AddCalculator",          # 工具名（LLM 靠这个识别）
    description="两个数字相加的计算器，输入 a 和 b，返回和",  # ← 这是给 LLM 看的"说明书"！
)


# ─── 3. 调用工具 ─────────────────────────────────────
if __name__ == "__main__":
    # 方式1：直接传字典
    result = calculator.invoke({"a": 10, "b": 25})
    print(f"计算结果: {result}")  # 输出 35

    # 方式2：打印工具的基本信息（看看 LLM 能看到什么）
    print("\n=== LLM 能看到的工具信息 ===")
    print(f"工具名：{calculator.name}")
    print(f"工具描述：{calculator.description}")
    print(f"参数格式（Schema）：")
    print(calculator.args_schema.model_json_schema())
