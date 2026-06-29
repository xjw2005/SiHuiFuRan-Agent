"""
展示：LLM 怎么看懂工具描述，自主决策调用

这就是 MokioAgent 里 planner_node 做的事情的简化版
"""
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


# 1. 定义两个工具
def add(a: int, b: int) -> int:
    """两个数相加，用这个工具做加法运算"""
    return a + b


def multiply(a: int, b: int) -> int:
    """两个数相乘，用这个工具做乘法运算"""
    return a * b


# 2. 包装成 StructuredTool
tools = [
    StructuredTool.from_function(func=add, name="Add", description="做加法"),
    StructuredTool.from_function(func=multiply, name="Multiply", description="做乘法"),
]

# 3. 把工具绑定给 LLM
model = ChatOpenAI(model="gpt-4o-mini", temperature=0, base_url="https://api.chatanywhere.tech", api_key="sk-gHew3VZBEFySnzRnsxQItaqijQ0EwjFqxSURt02KQuMVlHu7")
model_with_tools = model.bind_tools(tools)


# 4. 让 LLM 回答问题，看它会不会自己调用工具
if __name__ == "__main__":
    question = "123 乘以 456 等于多少？"
    print(f"用户问题：{question}")
    print("=" * 50)
    
    # LLM 接收到问题，会看工具描述，自主决定要不要调用工具
    response = model_with_tools.invoke(question)
    
    print(f"LLM 回复：")
    print(f"  内容: {response.content}")
    print(f"  要不要调用工具? {len(response.tool_calls) > 0}")
    
    if response.tool_calls:
        print(f"\nLLM 想要调用这些工具：")
        for call in response.tool_calls:
            print(f"  工具名: {call['name']}")
            print(f"  参数: {call['args']}")
            
            # 真正执行工具（对应 MokioAgent 里的 _execute_planner_tool）
            tool_map = {t.name: t for t in tools}
            result = tool_map[call["name"]].invoke(call["args"])
            
            print(f"  执行结果: {result}")
