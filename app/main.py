"""
SQL-Guardian FastAPI Service

Natural language to SQL translation API with human-in-the-loop approval for write operations.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import BaseMessage
from langgraph.types import Command

from .agent import sql_guardian_app


def _safe_content(value: Any) -> Any:
    """Return a JSON-serializable representation of message content."""
    if isinstance(value, (str, int, float, list, dict)) or value is None:
        return value
    return str(value)


def _serialize_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Serialize LangChain messages into JSON-friendly structures."""
    serialized: List[Dict[str, Any]] = []
    for message in messages:
        payload: Dict[str, Any] = {
            "type": getattr(message, "type", message.__class__.__name__.lower()),
            "content": _safe_content(getattr(message, "content", ""))
        }
        name = getattr(message, "name", None)
        if name:
            payload["name"] = name
        additional_kwargs = getattr(message, "additional_kwargs", None)
        if additional_kwargs:
            payload["additional_kwargs"] = additional_kwargs
        serialized.append(payload)
    return serialized


def _serialize_agent_outcome(agent_outcome: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Convert AgentAction/AgentFinish objects into serializable dictionaries."""
    if agent_outcome is None:
        return None
    if isinstance(agent_outcome, AgentAction):
        tool_input = agent_outcome.tool_input
        if not isinstance(tool_input, (dict, list, str, int, float, type(None))):
            tool_input = str(tool_input)
        return {
            "type": "action",
            "tool": agent_outcome.tool,
            "tool_input": tool_input,
            "log": agent_outcome.log
        }
    if isinstance(agent_outcome, AgentFinish):
        return {
            "type": "finish",
            "return_values": agent_outcome.return_values,
            "log": agent_outcome.log
        }
    return {
        "type": agent_outcome.__class__.__name__,
        "representation": repr(agent_outcome)
    }


# Initialize FastAPI application
app = FastAPI(
    title="SQL-Guardian Agent API",
    description="A natural language to SQL translation service with human-in-the-loop approval for write operations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "queries", "description": "Natural language query operations"},
        {"name": "approvals", "description": "Human approval workflow"},
        {"name": "status", "description": "Health and thread status"},
    ]
)


@app.get("/")
async def root():
    """API root endpoint with basic information and available endpoints."""
    return {
        "message": "Welcome to SQL-Guardian Agent API",
        "description": "A natural language to SQL translation service with human-in-the-loop approval for write operations",
        "version": "1.0.0",
        "endpoints": {
            "POST /query": "Submit a natural language query to be translated to SQL",
            "POST /mutations/approve": "Approve or reject proposed database mutations",
            "GET /threads/{thread_id}/state": "Check the status of a query execution thread",
            "GET /docs": "Interactive API documentation",
            "GET /redoc": "Alternative API documentation"
        },
        "usage": {
            "query_example": {
                "url": "/query",
                "method": "POST",
                "body": {"text": "Show me all employees in the sales department"}
            },
            "approval_example": {
                "url": "/mutations/approve", 
                "method": "POST",
                "body": {"thread_id": "uuid-here", "decision": "approve"}
            }
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "SQL-Guardian Agent API"}


class QueryRequest(BaseModel):
    """User query request model."""
    text: str


class ApprovalRequest(BaseModel):
    """Human approval request model supporting approve/reject/edit patterns."""
    thread_id: str
    decision: str  # "approve", "reject", or "edit"
    modified_sql: Optional[str] = None


@app.post("/query", tags=["queries"])
async def initiate_query(request: QueryRequest):
    """Execute natural language query with automatic SELECT execution or interrupt for write operations."""
    try:
        thread_id = str(uuid.uuid4())
        
        config = {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "query_type": "initial",
                "user_query": request.text[:100],
            },
            "tags": ["sql-guardian", "query-initiation"]
        }
        
        initial_state = {
            "input": request.text,
            "messages": [],
        }

        final_state = sql_guardian_app.invoke(initial_state, config=config)
        
        if "__interrupt__" in final_state:
            interrupt_data = final_state["__interrupt__"]
            state_snapshot = sql_guardian_app.get_state(config)
            stored_agent_outcome = state_snapshot.values.get("agent_outcome")
            serialized_outcome = _serialize_agent_outcome(stored_agent_outcome)
            return {
                "thread_id": thread_id,
                "status": "approval_required",
                "interrupt_data": interrupt_data,
                "agent_outcome": serialized_outcome,
                "message": "Approval is required for this database mutation.",
            }
        else:
            state_snapshot = sql_guardian_app.get_state(config)
            state_values = state_snapshot.values if state_snapshot else {}
            
            serialized_messages = _serialize_messages(state_values.get("messages", []))
            last_tool_result = state_values.get("last_tool_result")

            response_result = last_tool_result
            summary = "Query completed."
            stored_agent_outcome = state_values.get("agent_outcome")
            if isinstance(stored_agent_outcome, AgentFinish):
                summary = stored_agent_outcome.return_values.get('output', summary)
                response_result = response_result or summary

            return {
                "thread_id": thread_id,
                "status": "completed",
                "result": response_result,
                "summary": summary,
                "agent_outcome": None,
                "messages": serialized_messages,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@app.post("/mutations/approve", tags=["approvals"])
async def approve_mutation(request: ApprovalRequest):
    """Process human approval decision for write operations (approve/reject/edit)."""
    try:
        thread_id = request.thread_id
        decision = request.decision.strip().lower()
        
        config = {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "action": "approval",
                "decision": decision,
            },
            "tags": ["sql-guardian", "human-approval", decision]
        }
        
        try:
            current_state = sql_guardian_app.get_state(config)
            if not current_state or not current_state.values:
                raise HTTPException(status_code=404, detail="Thread not found")
        except Exception:
            raise HTTPException(status_code=404, detail="Thread not found")

        if decision == "reject":
            for chunk in sql_guardian_app.stream(Command(resume={"decision": "reject"}), config=config):
                pass
            return {
                "thread_id": thread_id,
                "status": "rejected",
                "message": "Database mutation was rejected. Workflow terminated.",
            }
        
        elif decision == "approve":
            for chunk in sql_guardian_app.stream(Command(resume={"decision": "approve"}), config=config):
                pass
            
            resumed_state = sql_guardian_app.get_state(config)
            resumed_values = resumed_state.values if resumed_state else {}
            last_tool_result = resumed_values.get("last_tool_result")
            agent_outcome = resumed_values.get("agent_outcome")
            summary = None
            if isinstance(agent_outcome, AgentFinish):
                summary = agent_outcome.return_values.get('output', 'Operation completed.')
            
            return {
                "thread_id": thread_id,
                "status": "approved_and_executed",
                "result": last_tool_result or summary,
                "summary": summary,
            }
        
        elif decision == "edit":
            if not request.modified_sql:
                raise HTTPException(
                    status_code=400, 
                    detail="modified_sql is required when decision is 'edit'"
                )
            
            for chunk in sql_guardian_app.stream(
                Command(resume={
                    "decision": "edit",
                    "modified_sql": request.modified_sql
                }), 
                config=config
            ):
                pass
            
            resumed_state = sql_guardian_app.get_state(config)
            resumed_values = resumed_state.values if resumed_state else {}
            last_tool_result = resumed_values.get("last_tool_result")
            agent_outcome = resumed_values.get("agent_outcome")
            summary = None
            if isinstance(agent_outcome, AgentFinish):
                summary = agent_outcome.return_values.get('output', 'Operation completed with human-edited SQL.')
            
            return {
                "thread_id": thread_id,
                "status": "edited_and_executed",
                "result": last_tool_result or summary,
                "summary": summary,
                "modified_sql": request.modified_sql,
            }
        
        else:
            raise HTTPException(
                status_code=400, 
                detail="Invalid decision. Must be 'approve', 'reject', or 'edit'"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing approval: {str(e)}")


@app.get("/threads/{thread_id}/state", tags=["status"])
async def get_thread_state(thread_id: str):
    """Retrieve current state of a thread for status polling."""
    config = {"configurable": {"thread_id": thread_id}}
    
    state = sql_guardian_app.get_state(config)
    
    if not state or not state.values:
        return {
            "thread_id": thread_id,
            "status": "not_found",
            "message": "Thread not found."
        }
    
    serialized_messages = _serialize_messages(state.values.get("messages", []))
    serialized_outcome = _serialize_agent_outcome(state.values.get("agent_outcome"))
    last_tool_result = state.values.get("last_tool_result")

    return {
        "thread_id": thread_id,
        "state": {
            "messages": serialized_messages,
            "agent_outcome": serialized_outcome,
            "last_tool_result": last_tool_result,
            "next": list(state.next) if state.next else [],
            "config": state.config,
            "metadata": state.metadata,
            "created_at": state.created_at.isoformat() if hasattr(state.created_at, "isoformat") else state.created_at,
            "parent_config": state.parent_config
        },
        "status": "pending" if state.next else "completed",
        "pending_action": serialized_outcome if state.next else None
    }