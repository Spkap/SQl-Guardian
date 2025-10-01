"""
SQL-Guardian LangGraph Agent with Human-in-the-Loop Logic

This module implements the core reasoning engine using a LangGraph state machine.
The agent uses ReAct-style reasoning to execute database queries with automatic
approval for SELECT queries and human-in-the-loop approval for write operations.
"""

import ast
import json
import re
from typing import Annotated, Any, List, Literal, Optional, Tuple, TypedDict, Union

from langchain.agents import create_react_agent
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .toolkits import all_tools, llm


WRITE_OPERATION_PATTERN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE|TRUNCATE|GRANT|REVOKE|MERGE)\b")
MAINTENANCE_PATTERN = re.compile(r"\b(ATTACH|DETACH|PRAGMA|VACUUM)\b")


class AgentState(TypedDict):
    """State definition for the SQL-Guardian agent."""
    input: str
    messages: Annotated[List[BaseMessage], add_messages]
    agent_outcome: Union[AgentAction, AgentFinish, None]
    last_tool_result: Optional[Any]
    intermediate_steps: List[Tuple[AgentAction, Any]]
    human_decision: Optional[str]


def _normalize_tool_result(result: Any) -> Any:
    """Normalize tool outputs into JSON-friendly Python primitives."""
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    if isinstance(result, str):
        trimmed = result.strip()
        if not trimmed:
            return ""
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(trimmed)
        except (ValueError, SyntaxError):
            return result
    return result


def execute_tool(tool_name: str, tool_input: Any, config: Optional[RunnableConfig] = None) -> Any:
    """Execute a tool by name with the given input and normalize the result."""
    for tool in all_tools:
        if tool.name == tool_name:
            try:
                result = tool.invoke(tool_input, config=config)
                return _normalize_tool_result(result)
            except Exception as e:
                return {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "tool": tool_name,
                    "message": f"Error executing {tool_name}: {str(e)}"
                }
    return {
        "error": "Tool not found",
        "tool": tool_name,
        "available_tools": [t.name for t in all_tools]
    }


react_prompt = PromptTemplate.from_template("""You are SQL-Guardian, an expert database assistant for natural language to SQL translation with safety controls.

# AVAILABLE DATABASES

## HR Database (hr_*)
- **departments**: id, name
- **employees**: id, name, email, hire_date, dept_id
- **salaries**: id, amount, effective_date, emp_id

## Sales Database (sales_*)
- **customers**: id, name, email
- **products**: id, name, price
- **orders**: id, created_at, customer_id
- **order_items**: id, quantity, unit_price, order_id, product_id

# SAFETY PROTOCOL

**SELECT queries**: Execute immediately
**Write operations (INSERT, UPDATE, DELETE, DROP, ALTER, etc.)**: Return SQL for human approval only

# AVAILABLE TOOLS
{tools}

# REASONING FORMAT

Question: the input question you must answer
Thought: analyze what information is needed and which database/tables to query
Action: the action to take, must be one of [{tool_names}]
Action Input: the precise input for the action (for SQL tools, provide valid SQL)
Observation: the result of the action
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now have sufficient information to answer
Final Answer: the complete answer to the user's question

---

Question: {input}
Thought: {agent_scratchpad}""")

agent = create_react_agent(llm, all_tools, react_prompt)


def run_agent(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """Execute the agent to determine the next action."""
    inputs = {
        "input": state["input"],
        "tools": all_tools,
        "tool_names": [tool.name for tool in all_tools],
        "agent_scratchpad": "",
        "intermediate_steps": state.get("intermediate_steps", [])
    }
    
    messages = state.get("messages", [])
    if messages:
        inputs["agent_scratchpad"] = "\n".join([str(msg) for msg in messages[-3:]])
    
    try:
        agent_outcome = agent.invoke(inputs, config=config)
        
        return {
            **state,
            "agent_outcome": agent_outcome
        }
    except Exception as e:
        error_message = f"Error during agent execution: {str(e)}"
        error_finish = AgentFinish(
            return_values={
                "output": f"I encountered an error while processing your request. Please provide more specific details or rephrase your query. Error: {str(e)[:100]}",
                "error": str(e),
                "error_type": type(e).__name__
            },
            log=error_message
        )
        return {
            **state,
            "agent_outcome": error_finish
        }


def execute_tools(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """Execute the tool chosen by the agent."""
    agent_outcome = state["agent_outcome"]
    
    if not isinstance(agent_outcome, AgentAction):
        return state
    
    result = execute_tool(agent_outcome.tool, agent_outcome.tool_input, config=config)

    messages = state.get("messages", [])
    tool_input_display = agent_outcome.tool_input
    if isinstance(tool_input_display, (dict, list)):
        tool_input_display = json.dumps(tool_input_display, indent=2, default=str)
    else:
        tool_input_display = str(tool_input_display)

    if isinstance(result, (dict, list)):
        result_display = json.dumps(result, indent=2, default=str)
    else:
        result_display = str(result)

    messages.append(
        AIMessage(
            content=(
                f"Tool: {agent_outcome.tool}\n"
                f"Input: {tool_input_display}\n"
                f"Result: {result_display}"
            )
        )
    )

    intermediate_steps = list(state.get("intermediate_steps", []))
    intermediate_steps.append((agent_outcome, result))

    return {
        **state,
        "messages": messages,
        "agent_outcome": None,
        "last_tool_result": result,
        "intermediate_steps": intermediate_steps
    }


def requires_human_approval(agent_outcome: Union[AgentAction, AgentFinish, None]) -> bool:
    """Check if an agent action or finish requires human approval for write operations."""
    if isinstance(agent_outcome, AgentAction):
        tool_input = agent_outcome.tool_input
        sql_query = ""
        if isinstance(tool_input, dict):
            sql_query = tool_input.get("query", "") or tool_input.get("sql", "") or tool_input.get("command", "")
        elif isinstance(tool_input, str):
            sql_query = tool_input

        sql_query_clean = re.sub(r"\s+", " ", sql_query).strip().upper()

        if not sql_query_clean:
            return False

        if sql_query_clean.startswith("SELECT"):
            return False

        if WRITE_OPERATION_PATTERN.search(sql_query_clean) or MAINTENANCE_PATTERN.search(sql_query_clean):
            return True

        return False

    elif isinstance(agent_outcome, AgentFinish):
        output = agent_outcome.return_values.get("output", "")
        log = agent_outcome.log or ""
        combined_text = f"{output} {log}".upper()
        
        if WRITE_OPERATION_PATTERN.search(combined_text) or MAINTENANCE_PATTERN.search(combined_text):
            return True
    
    return False

def human_approval_node(state: AgentState):
    """Interrupt the graph for human review of write operations."""
    agent_outcome = state.get("agent_outcome")
    
    sql_query = ""
    tool_name = None
    operation_type = "unknown"
    
    if isinstance(agent_outcome, AgentAction):
        tool_name = agent_outcome.tool
        tool_input = agent_outcome.tool_input
        if isinstance(tool_input, dict):
            sql_query = tool_input.get("query", "") or tool_input.get("sql", "") or tool_input.get("command", "")
        elif isinstance(tool_input, str):
            sql_query = tool_input
        
        sql_upper = sql_query.upper()
        if "INSERT" in sql_upper:
            operation_type = "INSERT"
        elif "UPDATE" in sql_upper:
            operation_type = "UPDATE"
        elif "DELETE" in sql_upper:
            operation_type = "DELETE"
        elif "DROP" in sql_upper:
            operation_type = "DROP"
        elif "ALTER" in sql_upper:
            operation_type = "ALTER"
        elif "CREATE" in sql_upper:
            operation_type = "CREATE"
            
    elif isinstance(agent_outcome, AgentFinish):
        sql_query = agent_outcome.return_values.get("output", "")
        operation_type = "FINISH"

    decision = interrupt(
        {
            "action_required": "review_and_approve",
            "operation_type": operation_type,
            "tool_name": tool_name,
            "sql_query": sql_query,
            "warning": "This operation will modify the database. Please review carefully.",
            "options": {
                "approve": "Execute the query as shown",
                "reject": "Cancel this operation",
                "edit": "Modify the query before execution (update state then resume)"
            },
            "instructions": "Respond with: {'decision': 'approve'|'reject'|'edit', 'modified_sql': '...' (if edit)}"
        }
    )

    return {"human_decision": decision}

def route_agent(state: AgentState) -> Literal["tools", "human_approval", "end"]:
    """Determine whether to execute tools, interrupt for approval, or end the workflow."""
    agent_outcome = state.get("agent_outcome")

    if requires_human_approval(agent_outcome):
        return "human_approval"

    if isinstance(agent_outcome, AgentFinish):
        return "end"

    if isinstance(agent_outcome, AgentAction):
        return "tools"
    
    return "end"

def after_human_approval(state: AgentState) -> Literal["tools", "end"]:
    """Determine the next step after human approval."""
    human_decision = state.get("human_decision")
    
    decision_value = None
    if isinstance(human_decision, dict):
        decision_value = human_decision.get("decision", "reject").lower()
        # Handle edit: update agent_outcome with modified SQL, then proceed as approval
        if decision_value == "edit" and "modified_sql" in human_decision:
            agent_outcome = state.get("agent_outcome")
            if isinstance(agent_outcome, AgentAction):
                modified_tool_input = agent_outcome.tool_input
                if isinstance(modified_tool_input, dict):
                    modified_tool_input["query"] = human_decision["modified_sql"]
                else:
                    modified_tool_input = human_decision["modified_sql"]
                state["agent_outcome"] = AgentAction(
                    tool=agent_outcome.tool,
                    tool_input=modified_tool_input,
                    log=agent_outcome.log + f"\n[Human edited SQL to: {human_decision['modified_sql']}]"
                )
            decision_value = "approve"
    elif isinstance(human_decision, str):
        decision_value = human_decision.lower()
    else:
        decision_value = str(human_decision).lower()
    
    if decision_value == "approve":
        if isinstance(state.get("agent_outcome"), AgentFinish):
            return "end"
        return "tools"
    return "end"

def create_sql_guardian_graph():
    """Create and compile the SQL-Guardian state graph with human-in-the-loop interrupts."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", run_agent)
    workflow.add_node("tools", execute_tools)
    workflow.add_node("human_approval", human_approval_node)
    
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        route_agent,
        {
            "tools": "tools",
            "human_approval": "human_approval",
            "end": END
        }
    )

    workflow.add_conditional_edges(
        "human_approval",
        after_human_approval,
        {
            "tools": "tools",
            "end": END
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    # MemorySaver enables interrupt/resume functionality for human approval
    checkpointer = MemorySaver()
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=[],
        interrupt_after=[]
    )
    
    return app


sql_guardian_app = create_sql_guardian_graph()

__all__ = ["sql_guardian_app", "AgentState"]