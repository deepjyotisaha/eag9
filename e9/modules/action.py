# modules/action.py

from typing import Dict, Any, Union
from pydantic import BaseModel
import asyncio
import types
import json
from config.log_config import setup_logging
from core.context import AgentContext
import yaml

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

    #import pdb; pdb.set_trace()

    # Create a fresh module scope
    sandbox = types.ModuleType("sandbox")

    try:
        # Check if sandbox failure simulation is enabled
        try:
            with open("config/profiles.yaml", "r") as f:
                config = yaml.safe_load(f)
                simulate_failure = config.get("strategy", {}).get("simulate_sandbox_failure", False)
        except Exception as e:
            logger.error(f"[action] 🔍 Failed to load config or parse simulate_sandbox_failure: {e}")
            simulate_failure = False

        # Patch MCP client with real dispatcher and context
        class SandboxMCP:
            def __init__(self, dispatcher, context):
                self.dispatcher = dispatcher
                self.call_count = 0
                self.memory = context.memory
                self.simulate_failure = simulate_failure

            async def call_tool(self, tool_name: str, input_dict: dict):
                self.call_count += 1
                if self.call_count > MAX_TOOL_CALLS_PER_PLAN:
                    raise RuntimeError(f"Exceeded max tool calls ({MAX_TOOL_CALLS_PER_PLAN}) in solve() plan.")
                
                # If failure simulation is enabled, force failure for call_tool
                if self.simulate_failure:
                    logger.info(f"[action] 🔍 Simulating tool call failure for: {tool_name}")
                    raise ValueError("Tool execution failed")
                
                logger.info(f"[action] 🔍 Calling actual tool inside sandbox: {tool_name}")
                result = await self.dispatcher.call_tool(tool_name, input_dict)
                logger.info(f"[action] 🔍 Result of tool call: {result}")
                return result

            def get_tool_results_from_cache(self, tools):
                """Access memory manager's get_tool_results_from_cache"""
                # Always allow cache access, even when simulate_failure is True
                return self.memory.get_tool_results_from_cache(tools)

        sandbox.mcp = SandboxMCP(dispatcher, context)

        # Create a standalone function that uses the mcp instance
        def get_tool_results_from_cache(tool_name):
            # Get lookback days from config
            try:
                with open("config/profiles.yaml", "r") as f:
                    config = yaml.safe_load(f)
                lookback_tool_results = config.get("memory", {}).get("lookback_tool_results", 2)
                logger.info(f"[action] 🔍 Using lookback_tool_results={lookback_tool_results} from config")
            except Exception as e:
                logger.error(f"[action] 🔍 Failed to load config or parse lookback_tool_results: {e}")
                lookback_tool_results = 2  # Default to 2 if config fails
            
            #import pdb; pdb.set_trace()
            cached_results = sandbox.mcp.get_tool_results_from_cache([tool_name])
            if cached_results and len(cached_results) > 0:
                # Get the most recent results up to lookback_tool_results
                results = cached_results[:lookback_tool_results]
                logger.info(f"[action] 🔍 Found {len(results)} cached results for tool: {tool_name}")
                # Return the most recent result
                return results[0].tool_result
            logger.info(f"[action] 🔍 No cached results found for tool: {tool_name}")
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
