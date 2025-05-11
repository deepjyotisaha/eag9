# modules/action.py

from typing import Dict, Any, Union
from pydantic import BaseModel
import asyncio
import types
import json
from config.log_config import setup_logging
from core.context import AgentContext

logger = setup_logging(__name__)

# Optional logging fallback
#try:
#    from agent import log
#except ImportError:
#    import datetime
#    def log(stage: str, msg: str):
#        now = datetime.datetime.now().strftime("%H:%M:%S")
#        print(f"[{now}] [{stage}] {msg}")

class ToolCallResult(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Union[str, list, dict]
    raw_response: Any

MAX_TOOL_CALLS_PER_PLAN = 5

async def run_python_sandbox(code: str, dispatcher: Any, context: AgentContext) -> str:
    logger.info("[action] 🔍 Entered run_python_sandbox()")

    # Create a fresh module scope
    sandbox = types.ModuleType("sandbox")

    try:
        # Patch MCP client with real dispatcher and context
        class SandboxMCP:
            def __init__(self, dispatcher, context):
                self.dispatcher = dispatcher
                self.call_count = 0
                self.memory = context.memory

            async def call_tool(self, tool_name: str, input_dict: dict):
                self.call_count += 1
                if self.call_count > MAX_TOOL_CALLS_PER_PLAN:
                    raise RuntimeError(f"Exceeded max tool calls ({MAX_TOOL_CALLS_PER_PLAN}) in solve() plan.")
                logger.info(f"[action] 🔍 Calling actual tool inside sandbox: {tool_name}")
                result = await self.dispatcher.call_tool(tool_name, input_dict)
                import pdb; pdb.set_trace()
                logger.info(f"[action] 🔍 Result of tool call: {result}")
                #result = RuntimeError("Tool execution failed")
                logger.info(f"[action] 🔍 Forcing tool execution to fail: {result}")
                raise ValueError("Tool execution failed")
                return result

            def get_tool_results_from_cache(self, tools):
                """Access memory manager's get_tool_results_from_cache"""
                return self.memory.get_tool_results_from_cache(tools)

        sandbox.mcp = SandboxMCP(dispatcher, context)

         # Create a standalone function that uses the mcp instance
        def get_tool_results_from_cache(tool_name):
            cached_results = sandbox.mcp.get_tool_results_from_cache([tool_name])
            if cached_results and len(cached_results) > 0:
                # Get the most recent result
                latest_result = cached_results[0]
                # Return the exact tool_result as it was stored
                return latest_result.tool_result
            return None

        # Preload safe built-ins into the sandbox
        import json, re
        sandbox.__dict__["json"] = json
        sandbox.__dict__["re"] = re
        sandbox.__dict__["get_tool_results_from_cache"] = get_tool_results_from_cache

        # Execute solve fn dynamically
        logger.info(f"[action] 🔍 Now executing solve fn dynamically")
        exec(compile(code, "<solve_plan>", "exec"), sandbox.__dict__)

        solve_fn = sandbox.__dict__.get("solve")
        if solve_fn is None:
            raise ValueError("No solve() function found in plan.")

        if asyncio.iscoroutinefunction(solve_fn):
            logger.info(f"[action] 🔍 Executing solve fn asynchronously")
            result = await solve_fn()
        else:
            logger.info(f"[action] 🔍 Executing solve fn synchronously")
            result = solve_fn()
            
        logger.info(f"[action] 🔍 Result of solve fn: {result}")

         # Clean result formatting
        if isinstance(result, dict) and "result" in result:
            return f"{result['result']}"
        elif isinstance(result, dict):
            return f"{json.dumps(result)}"
        elif isinstance(result, list):
            return f"{' '.join(str(r) for r in result)}"
        else:
            return f"{result}"






    except Exception as e:
        logger.error(f"[action] ⚠️ sandbox execution error: {e}")
        return f"[sandbox error: {str(e)}]"
