import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()


# 定义 State

class ReflectionState(TypedDict):
    
    messages: Annotated[list, add_messages]
    task: str
    iteration: int
    max_iterations: int
    arrival_max_iterations: bool
    is_satisfactory: bool


llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    temperature=0.7,
    base_url=os.getenv("OPENAI_BASE_URL"),
)

GENERATE_PROMPT = """你是一个专业的助手。请认真回答以下问题：

{task}

请给出清晰、准确、有深度的回答。"""

def generate_node(state: ReflectionState) -> dict:
    """生成节点：让 LLM 根据 task 生成答案"""
    print(f"\n{'='*60}")
    print(f"[迭代 {state['iteration'] + 1}] 📝 GENERATE — 正在生成答案...")

    response = llm.invoke(
        GENERATE_PROMPT.format(task=state["task"])
    )
    print(f"生成内容（前200字）：\n{response.content[:200]}...")

    return {
        "messages": [response],
        "iteration": state["iteration"] + 1,
    }

REFLECT_PROMPT = """你是一个严格的评审专家。请对以下回答进行批判性反思，判断其质量是否合格。

【原始任务】
{task}

【待评审的回答】
{answer}

请从以下维度评判：
1. 是否准确回答了问题？
2. 是否有逻辑漏洞或事实错误？
3. 是否足够清晰、完整？
4. 是否有改进空间？

最后，请以如下格式给出结论（必须严格遵守格式）：
SATISFACTORY: yes  或  SATISFACTORY: no

如果答案是 "no"，请简要说明哪里需要改进。"""


def reflect_node(state: ReflectionState) -> dict:
    """反思节点：让 LLM 对自己的回答进行评审"""
    print(f"\n[迭代 {state['iteration']}] 🔍 REFLECT — 正在反思答案...")

    answer = state["messages"][-1].content

    response = llm.invoke(
        REFLECT_PROMPT.format(task=state["task"], answer=answer)
    )
    print(f"反思结果：\n{response.content[:300]}...")

    # 解析反思结果
    is_satisfactory = "SATISFACTORY: yes" in response.content.lower()

    # 更新状态
    if state["iteration"] >= state["max_iterations"]:
        state["arrival_max_iterations"] = True
 
    return {
        "messages": [response],
        "is_satisfactory": is_satisfactory,
    }


REVISE_PROMPT = """你是一个追求卓越的助手。评审专家对你的上一个回答提出了以下改进意见：

【原始任务】
{task}

【你的上一版回答】
{answer}

【评审专家的反馈】
{feedback}

请根据反馈，重新给出一个改进后的回答。要求：
1. 保留原回答中的所有正确内容
2. 针对反馈中指出的问题进行修正
3. 补充遗漏的重要信息
4. 让回答更加准确和完整"""

def revise_node(state: ReflectionState) -> dict:
    """修订节点：根据反思反馈修改答案"""
    print(f"\n[迭代 {state['iteration']}] ✏️  REVISE — 正在根据反馈修改答案...")

    # messages[-2] 是 answer，messages[-1] 是 reflect 的反馈
    answer = state["messages"][-2].content
    feedback = state["messages"][-1].content

    response = llm.invoke(
        REVISE_PROMPT.format(task=state["task"], answer=answer, feedback=feedback)
    )
    print(f"修订内容（前200字）：\n{response.content[:200]}...")

    return {
        "messages": [response],
    }



def should_continue(state: ReflectionState) -> str:
    """决定是否继续反思循环"""
    if state["is_satisfactory"]:
        print(f"\n✅ 反思通过！答案质量合格。")
        return "end"
    if state["iteration"] > state["max_iterations"]:
        print(f"\n⚠️  达到最大迭代次数 ({state['max_iterations']})，强制结束。")
        return "end"
    print(f"\n🔄 答案需要改进，进入第 {state['iteration'] + 1} 轮修订...")
    return "reflect"



def build_reflection_graph() -> CompiledStateGraph:

    workflow = StateGraph(ReflectionState)

    # Add nodes
    workflow.add_node("generate", generate_node)
    workflow.add_node("reflect", reflect_node)
    # workflow.add_node("revise", revise_node)



    workflow.set_entry_point("generate")

    workflow.add_edge("generate", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        should_continue,
        {
            "reflect": "generate",
            "end": END,
        }
    )
    return workflow.compile(checkpointer=MemorySaver())




def main():
    print("=" * 60)
    print("🧠 LangGraph Reflection Pattern Demo")
    print("=" * 60)

    task = "什么是大语言模型的思维链（Chain-of-Thought）推理？请用通俗易懂的语言解释，并举例说明。"

    initial_state: ReflectionState = {
        "messages": [],
        "task": task,
        "iteration": 0,
        "max_iterations": 3,
        "arrival_max_iterations": False,
        "is_satisfactory": False,
    }

    graph = build_reflection_graph()

    config = {"configurable": {"thread_id": "demo‘s demo-01"}}
    final_state = graph.invoke(initial_state, config)

    print("\n" + "=" * 60)
    print("🏁 最终答案：")
    print("=" * 60)
    # 最终答案是最新一条消息（最后一次 generate 或 revise 的输出）
    print("Test: The Bool of arrival_max_iterations is: ", final_state["arrival_max_iterations"])
    final_answer = final_state["messages"][-2].content
    print(final_answer)

    print(f"\n📊 统计：共进行 {final_state['iteration']} 轮迭代")


if __name__ == "__main__":
    main()
