# Bug Fix Report and Cache Memory Implementation

## Original Bugs Fixed

### Bug 1. Decision was not seeing perception and memory outputs
**Problem:**
- Decision module was not receiving perception and memory data
- Caused by improper data flow between modules

**Fix Implementation:**
```python
# In core/loop.py
async def run(self):
    # ... existing code ...
    

    # Perception inputs and get_session items were added to give memory results to desicion
    #    
    plan = await generate_plan(
        user_input=self.context.user_input,
        perception=perception,
        context=self.context,
        memory_items=self.context.memory.get_session_items(),
        tool_descriptions=tool_descriptions,
        tool_output_from_cache=memory_lookup_tool_results,  # Added cache results
        prompt_path=prompt_path,
        step_num=step + 1,
        max_steps=max_steps,
        lifelines_left=lifelines_left,
    )
```

### Bug 2. Tool Outputs were not being saved to memory 
**Problem:**
- Tool execution results weren't being persisted
- Decision module couldn't access previous tool outputs

**Fix Implementation:**
```python
# In core/loop.py
    # After tool execution
    self.context.memory.add_tool_output(
        tool_name="solve_sandbox",
        tool_args={"plan": plan},
        tool_result={"result": result},
        success=True,
        tags=["sandbox"],
    )
    logger.info(f"Adding tool output to memory: {result}")
```

### Bug 3. Incorrect prompt examples in Decision Prompt
**Problem:**
- Decision prompts had incorrect or outdated examples
- Caused confusion in tool selection and execution

**Fix Implementation:**
- Updated prompt templates with correct examples
- Added validation for prompt examples
- Implemented proper error handling for prompt generation
- Added cache-aware decision prompts:
  - `prompts/decision_prompt_conservative_optimized.txt` - Cache-enabled prompt
  - `prompts/decision_prompt_conservative_optimized_no_cache.txt` - No-cache prompt
- Implemented cache fallback configuration in profiles.yaml:
```yaml
strategy:
    cache_fallback: false          # When true, uses cache-enabled prompt, otherwise uses no-cache prompt
```

## Cache Memory Implementation

### Step 1: LLM Code Generation for solve() with Cache Awareness
The system uses two different prompts to guide the LLM in generating the `solve()` function:

1. **Cache-Enabled Prompt** (`decision_prompt_conservative_optimized.txt`):
   - Includes cache-specific instructions for the LLM
   - Provides access to `get_tool_results_from_cache(tool_name, input)` function
   - Instructs LLM to use cache when:
     - There are sandbox/tool execution errors
     - Only 1 lifeline is left in the current step
   - Requires LLM to add note when using cached results: "[NOTE: This answer was obtained from cached results due to tool error encountered during execution]"

2. **No-Cache Prompt** (`decision_prompt_conservative_optimized_no_cache.txt`):
   - Simplified version without cache functionality
   - Focuses on direct tool execution
   - Uses available tool results from session memory
   - No cache-related functions or instructions

The LLM generates code based on these patterns:

```python

cached_result = get_tool_results_from_cache(tool_name, input)
return f"FURTHER_PROCESSING_REQUIRED: {{cached_result}}.

```
The cache fallback is controlled by the `cache_fallback` setting in `profiles.yaml`:
```yaml
strategy:
  cache_fallback: true  # When true, uses cache-enabled prompt
```

This implementation ensures that:
1. The LLM is aware of cache availability when configured
2. Cache is used as a fallback mechanism when tools fail
3. Users are informed when cached results are used
4. The system can operate without cache when needed

### Step 2: Sandbox code executes the function to fetch cached tool results from cached memory

The cached tool result is then fetched via the execution in sandbox:

```python
# In modules/action.py
async def run_python_sandbox(code: str, dispatcher: Any) -> str:
    print("[action] 🔍 Entered run_python_sandbox()")

    # Create a fresh module scope
    sandbox = types.ModuleType("sandbox")

    try:
        # Patch MCP client with real dispatcher
        class SandboxMCP:
            def __init__(self, dispatcher):
                self.dispatcher = dispatcher
                self.call_count = 0

            async def call_tool(self, tool_name: str, input_dict: dict):
                self.call_count += 1
                if self.call_count > MAX_TOOL_CALLS_PER_PLAN:
                    raise RuntimeError(f"Exceeded max tool calls ({MAX_TOOL_CALLS_PER_PLAN}) in solve() plan.")
                
                # Try to get result from cache first
                cached_result = self.dispatcher.context.memory.get_tool_results_from_cache([tool_name])
                if cached_result:
                    logger.info(f"Using cached result for {tool_name}")
                    return cached_result
                
                # If no cache, make the actual tool call
                result = await self.dispatcher.call_tool(tool_name, input_dict)
                return result
```

## Configuration Updates

```yaml
# In profiles.yaml
memory:
  memory_service: true
  summarize_tool_results: true
  tag_interactions: true
  storage:
    base_dir: "memory"
    structure: "date"
  lookback_days: 7
  lookback_tool_results: 8
```