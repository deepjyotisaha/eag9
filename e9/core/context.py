# core/context.py

from typing import List, Optional, Dict, Any
from modules.memory import MemoryManager, MemoryItem
from core.session import MultiMCP  # For dispatcher typing
from pathlib import Path
import yaml
import time
import uuid
from datetime import datetime
from pydantic import BaseModel

class StrategyProfile(BaseModel):
    planning_mode: str
    exploration_mode: Optional[str] = None
    memory_fallback_enabled: bool
    max_steps: int
    max_lifelines_per_step: int
    cache_fallback: bool = True  # Default to True for backward compatibility


class AgentProfile:
    def __init__(self):
        with open("config/profiles.yaml", "r") as f:
            config = yaml.safe_load(f)

        self.name = config["agent"]["name"]
        self.id = config["agent"]["id"]
        self.description = config["agent"]["description"]

        self.strategy = StrategyProfile(**config["strategy"])
        self.memory_config = config["memory"]
        self.llm_config = config["llm"]
        self.persona = config["persona"]


    def __repr__(self):
        return f"<AgentProfile {self.name} ({self.strategy})>"

class AgentContext:
    """Holds all session state, user input, memory, and strategies."""

    def __init__(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        dispatcher: Optional[MultiMCP] = None,
        mcp_server_descriptions: Optional[List[Any]] = None,
    ):
        if session_id is None:
            today = datetime.now()
            ts = int(time.time())
            uid = uuid.uuid4().hex[:6]
            session_id = f"{today.year}/{today.month:02}/{today.day:02}/session-{ts}-{uid}"

        #if session_id is None:
        #    today = datetime.now()
        #    ts = int(time.time())
        #    uid = uuid.uuid4().hex[:6]
        #    session_id = f"{today.year}{today.month:02}{today.day:02}_{ts}_{uid}"

        self.user_input = user_input
        self.agent_profile = AgentProfile()
        self.memory = MemoryManager(session_id=session_id)
        self.session_id = self.memory.session_id
        self.dispatcher = dispatcher  # 🆕 Added formally
        self.mcp_server_descriptions = mcp_server_descriptions  # 🆕 Added formally
        self.step = 0
        self.task_progress = []  # 🆕 Will track tool executions
        self.final_answer = None
        

        # Log session start
        self.add_memory(MemoryItem(
            timestamp=time.time(),
            text=f"Started new session with input: {user_input} at {datetime.utcnow().isoformat()}",
            type="run_metadata",
            session_id=self.session_id,
            tags=["run_start"],
            user_query=user_input,
            metadata={
                "start_time": datetime.now().isoformat(),
                "step": self.step
            }
        ))

    def add_memory(self, item: MemoryItem):
        """Add item to memory"""
        self.memory.add(item)


    def format_sandbox_execution_history(self, memory_items, max_text_length=200):
        """
        Format memory items into a structured response showing sandbox execution history.
        Limits large text chunks to make output more readable.
        
        Args:
            memory_items: List of MemoryItem objects from the session
            max_text_length: Maximum length for text chunks before truncation
            
        Returns:
            str: Formatted string showing execution history
        """
        def truncate_text(text, max_length):
            """Helper function to truncate text with ellipsis"""
            if len(text) > max_length:
                return text[:max_length] + "..."
            return text

        def extract_content(result):
            """Helper function to extract and clean content from tool results"""
            if not result:
                return "No result"
            
            # Try to extract content from TextContent
            if "content=" in result:
                try:
                    content_text = result.split("content=")[1].split("text='")[1].split("'")[0]
                    # Clean up escaped characters
                    content_text = content_text.replace("\\n", "\n").replace("\\'", "'")
                    return truncate_text(content_text, max_text_length)
                except:
                    return truncate_text(result, max_text_length)
            return truncate_text(result, max_text_length)

        formatted_history = []
        current_sandbox = None
        
        for item in memory_items:
            # Only process tool_output items with sandbox tag
            if item.type == "tool_output" and "sandbox" in item.tags:
                # Start new sandbox execution section
                if current_sandbox is None:
                    current_sandbox = []
                    formatted_history.append("Attempt to execute sandbox was done with the following outcomes:")
                
                # Extract plan from tool_args
                plan = item.tool_args.get("plan", "")
                
                # Extract tool calls and their names from plan
                tool_calls = []
                for line in plan.split("\n"):
                    if "FUNCTION_CALL:" in line:
                        # Extract tool name from the next line that contains the tool call
                        next_line = plan.split("\n")[plan.split("\n").index(line) + 1]
                        if "await mcp.call_tool(" in next_line:
                            tool_name = next_line.split("'")[1]  # Get tool name from the call
                            # Truncate the tool call line if it's too long
                            tool_call = truncate_text(next_line.strip(), max_text_length)
                            tool_calls.append((tool_name, tool_call))
                
                # Add tool results
                if item.tool_result and "result" in item.tool_result:
                    result = item.tool_result["result"]
                    # Add each tool call and its result
                    for tool_name, tool_call in tool_calls:
                        formatted_history.append(f"1. Called tool '{tool_name}' with: {tool_call}")
                        formatted_history.append(f"2. Tool '{tool_name}' returned: {extract_content(result)}")
                
                # Add final sandbox result
                if item.success:
                    formatted_history.append(f"Finally sandbox returned: {extract_content(result)}")
                else:
                    formatted_history.append(f"Finally sandbox failed with: {extract_content(result)}")
                
                # Add separator between different sandbox executions
                formatted_history.append("---")
                current_sandbox = None
        
        return "\n".join(formatted_history)    

    def format_history_for_llm(self) -> str:
        if not self.tool_calls:
            return "No previous actions"
            
        history = []
        for i, trace in enumerate(self.tool_calls, 1):
            result_str = str(trace.result)
            if i < len(self.tool_calls):  # Previous steps
                if len(result_str) > 50:
                    result_str = f"{result_str[:50]}... [RESPONSE TRUNCATED]"
            # else: last step gets full result
            
            history.append(f"{i}. Used {trace.tool_name} with {trace.arguments}\nResult: {result_str}")
        
        return "\n\n".join(history)

    def log_subtask(self, tool_name: str, status: str = "pending"):
        """Log the start of a new subtask."""
        self.task_progress.append({
            "step": self.step,
            "tool": tool_name,
            "status": status,
        })

    def update_subtask_status(self, tool_name: str, status: str):
        """Update the status of an existing subtask."""
        for item in reversed(self.task_progress):
            if item["tool"] == tool_name and item["step"] == self.step:
                item["status"] = status
                break

    def __repr__(self):
        return f"<AgentContext step={self.step}, session_id={self.session_id}>"
