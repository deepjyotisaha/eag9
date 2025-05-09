# modules/tools.py

from typing import List, Dict, Optional, Any
import re
from config.log_config import setup_logging
from modules.memory import MemoryItem, MemoryManager

logger = setup_logging(__name__)

def extract_json_block(text: str) -> str:
    match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def summarize_tools(tools: List[Any]) -> str:
    """
    Generate a string summary of tools for LLM prompt injection.
    Format: "- tool_name: description"
    """
    logger.debug(f"[tools] Summarizing tools: {tools}")
    return "\n".join(
        f"- {tool.name}: {getattr(tool, 'description', 'No description provided.')}"
        for tool in tools
    )


def filter_tools_by_hint(tools: List[Any], hint: Optional[str] = None) -> List[Any]:
    """
    If tool_hint is provided (e.g., 'search_documents'),
    try to match it exactly or fuzzily with available tool names.
    """
    if not hint:
        return tools

    hint_lower = hint.lower()
    filtered = [tool for tool in tools if hint_lower in tool.name.lower()]
    return filtered if filtered else tools


def get_tool_map(tools: List[Any]) -> Dict[str, Any]:
    """
    Return a dict of tool_name → tool object for fast lookup
    """
    return {tool.name: tool for tool in tools}

def tool_expects_input(self, tool_name: str) -> bool:
    tool = next((t for t in self.tools if t.name == tool_name), None)
    if not tool or not hasattr(tool, 'parameters') or not isinstance(tool.parameters, dict):
        return False
    # If the top-level parameter is just 'input', we assume wrapping is required
    return list(tool.parameters.keys()) == ['input']


def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
    

def get_tool_output_from_cache(tool_name: str, memory_items: List[MemoryItem]) -> Optional[str]:
    """
    Get the most recent successful tool output from cache for a specific tool.
    
    Args:
        tool_name (str): The name of the tool to search for
        memory_items (List[MemoryItem]): List of memory items to search through
        
    Returns:
        Optional[str]: The most recent successful tool output result, or None if not found
    """
    # Search from newest to oldest for the most recent successful output
    for item in reversed(memory_items):
        if (item.type == "tool_output" and 
            item.tool_name == tool_name and 
            item.success and 
            item.tool_result is not None):
            
            # Extract the result from tool_result
            if isinstance(item.tool_result, dict) and "result" in item.tool_result:
                return item.tool_result["result"]
            elif isinstance(item.tool_result, str):
                return item.tool_result
            else:
                return str(item.tool_result)
    
    return None


