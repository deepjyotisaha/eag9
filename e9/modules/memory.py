# modules/memory.py

import json
import os
import time
import yaml
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pydantic import BaseModel
from config.log_config import setup_logging
import difflib
from fuzzywuzzy import fuzz

logger = setup_logging(__name__)

class MemoryItem(BaseModel):
    """Represents a single memory entry for a session."""
    timestamp: float
    type: str  # run_metadata, tool_call, tool_output, final_answer
    text: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[dict] = None
    final_answer: Optional[str] = None
    tags: Optional[List[str]] = []
    success: Optional[bool] = None
    metadata: Optional[dict] = {}  # ✅ ADD THIS LINE BACK


class MemoryManager:
    """Manages session memory (read/write/append)."""

    def __init__(self, session_id: str, memory_dir: str = "memory"):
        logger.info(f"Initializing MemoryManager for session_id: {session_id}")
        self.session_id = session_id
        self.memory_dir = memory_dir
        #self.memory_path = os.path.join('memory', session_id.split('-')[0], session_id.split('-')[1], session_id.split('-')[2], f'session-{session_id}.json')
        # Parse session_id to extract date and unique session string
        parts = session_id.split('/')
        year, month, day, session_file = parts[0], parts[1], parts[2], parts[3]
        self.memory_path = os.path.join(
            'memory',
            year,
            month,
            day,
            f"{session_file}.json"
        )
        logger.info(f"Memory path: {self.memory_path}")
        logger.info(f"Memory dir: {self.memory_dir}")
        logger.info(f"Session id: {self.session_id}")
        self.items: List[MemoryItem] = []
        self.cached_memory_all = []
        self.cached_memory_lookup_queries = []

        logger.info(f"Memory path: {self.memory_path}")
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)

        self.load()
        self.load_cached_memory()

    def load(self):
        self.items = []
        #logger.info(f"Loading memory from {self.memory_path}")
        #if os.path.exists(self.memory_path):
        #    with open(self.memory_path, "r", encoding="utf-8") as f:
        #        raw = json.load(f)
        #        #self.items = [MemoryItem(**item) for item in raw]
        #        logger.info(f"Loaded {len(self.items)} items from {self.memory_path}")
        #else:
        #    logger.info(f"Memory file does not exist at {self.memory_path}")
        #    self.items = []

    def load_cached_memory(self, config_path="config/profiles.yaml"):
        """
        Loads all memory items from the last X days, where X is configured in profiles.yaml.
        Returns a list of MemoryItem objects.
        """

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            lookback_days = config.get("memory", {}).get("lookback_days", 7)
            base_dir = config.get("memory", {}).get("storage", {}).get("base_dir", "memory")
        except Exception as e:
            logger.error(f"Failed to load config or parse lookback_days: {e}")
            lookback_days = 7
            base_dir = "memory"

        today = datetime.today()
        all_items = []

        for i in range(lookback_days):
            try:
                day = today - timedelta(days=i)
                year = str(day.year)
                month = f"{day.month:02}"
                day_str = f"{day.day:02}"
                day_dir = os.path.join(base_dir, year, month, day_str)
                if not os.path.exists(day_dir):
                    continue
                date_str = f"{year}-{month}-{day_str}"
                logger.debug(f"Loading cache for date: {date_str}")
                for fname in os.listdir(day_dir):
                    if fname.endswith(".json"):
                        fpath = os.path.join(day_dir, fname)
                        try:
                            logger.debug(f"Loading cache for {fpath}")
                            with open(fpath, "r", encoding="utf-8") as f:
                                raw = json.load(f)
                                items = [MemoryItem(**item) for item in raw]
                                all_items.extend(items)
                        except Exception as e:
                            logger.warning(f"Failed to load or parse {fpath}: {e}")
            except Exception as e:
                logger.warning(f"Error processing directory for day {i} ({day_dir}): {e}")
        self.cached_memory_all = all_items
        logger.info(f"Loaded {len(self.cached_memory_all)} items from cached memory")
       
    

    def save(self):
        # Before opening the file for writing
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            raw = [item.dict() for item in self.items]
            json.dump(raw, f, indent=2)

    def add(self, item: MemoryItem):
        self.items.append(item)
        self.save()

    def add_tool_call(
        self, tool_name: str, tool_args: dict, tags: Optional[List[str]] = None
    ):
        item = MemoryItem(
            timestamp=time.time(),
            type="tool_call",
            text=f"Called {tool_name} with {tool_args}",
            tool_name=tool_name,
            tool_args=tool_args,
            tags=tags or [],
        )
        self.add(item)

    def add_tool_output(
        self, tool_name: str, tool_args: dict, tool_result: dict, success: bool, tags: Optional[List[str]] = None
    ):
        item = MemoryItem(
            timestamp=time.time(),
            type="tool_output",
            text=f"Output of {tool_name}: {tool_result}",
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            success=success,  # 🆕 Track success!
            tags=tags or [],
        )
        self.add(item)

    def add_final_answer(self, text: str):
        item = MemoryItem(
            timestamp=time.time(),
            type="final_answer",
            text=text,
            final_answer=text,
        )
        self.add(item)

    def find_recent_successes(self, limit: int = 5) -> List[str]:
        """Find tool names which succeeded recently."""
        tool_successes = []

        # Search from newest to oldest
        for item in reversed(self.items):
            if item.type == "tool_output" and item.success:
                if item.tool_name and item.tool_name not in tool_successes:
                    tool_successes.append(item.tool_name)
            if len(tool_successes) >= limit:
                break

        return tool_successes

    def add_tool_success(self, tool_name: str, success: bool):
        """Patch last tool call or output for a given tool with success=True/False."""

        # Search backwards for latest matching tool call/output
        for item in reversed(self.items):
            if item.tool_name == tool_name and item.type in {"tool_call", "tool_output"}:
                item.success = success
                logger.info(f"✅ Marked {tool_name} as success={success}")
                self.save()
                return

        logger.warning(f"⚠️ Tried to mark {tool_name} as success={success} but no matching memory found.")

    def get_session_items(self) -> List[MemoryItem]:
        """
        Return all memory items for current session.
        """
        return self.items
    
    def get_tool_results_from_cache(self, selected_tools=None, input_params=None):
        """
        Returns a list of the last N tool outputs from cached memory for the selected tools,
        where N is the lookback_days configured in profiles.yaml.
        If selected_tools is None, returns None.
        """
        #import pdb; pdb.set_trace()

        if selected_tools is None:
            logger.info("No selected_tools provided; returning None.")
            return None

        # Get tool names from selected_tools
        tool_names = [t.name if hasattr(t, "name") else t for t in selected_tools]
        logger.info(f"Looking for tool outputs for tools: {tool_names}")
        
        # Get lookback days from config
        try:
            with open("config/profiles.yaml", "r") as f:
                config = yaml.safe_load(f)
            lookback_tool_results = config.get("memory", {}).get("lookback_tool_results", 2)
            logger.info(f"Using lookback_tool_results={lookback_tool_results} from config")
        except Exception as e:
            logger.error(f"Failed to load config or parse lookback_tool_results: {e}")
            lookback_tool_results = 7

        # Get all items from cached memory
        all_items = self.cached_memory_all
        logger.info(f"Total items in cached memory: {len(all_items)}")
        
        # Track the last N outputs for each tool
        tool_outputs = {tool_name: [] for tool_name in tool_names}
        logger.info(f"Initialized tool_outputs tracking for: {list(tool_outputs.keys())}")

        # Process items in chronological order (newest first)
        for item in all_items:
            # Only process successful tool outputs
            if item.type != "tool_output" or not item.success:
                continue

            # Log each tool_output item we're processing
            #logger.info(f"Processing tool_output item: {item.__dict__}")
            logger.info(f"Processing tool_output item: {str(item.__dict__)[:200]}...")
            
            # Extract actual tool name from tool_args.plan
            if hasattr(item, 'tool_args') and isinstance(item.tool_args, dict) and 'plan' in item.tool_args:
                plan = item.tool_args['plan']
                # Look for mcp.call_tool('tool_name', input) pattern
                import re
                tool_call_match = re.search(r"await\s+mcp\.call_tool\s*\(\s*['\"]([^'\"]+)['\"]", plan)
                if tool_call_match:
                    actual_tool_name = tool_call_match.group(1)
                    logger.info(f"Extracted actual tool name from plan: {actual_tool_name}")
                    
                    # Check if this item is for one of our selected tools
                    for tool_name in tool_names:
                        if actual_tool_name == tool_name:
                            logger.info(f"Found match for tool '{tool_name}' in item")
                            # If we haven't collected N outputs for this tool yet, add it
                            if len(tool_outputs[tool_name]) < lookback_tool_results:
                                tool_outputs[tool_name].append(item)
                                logger.info(f"Added item to outputs for '{tool_name}' (now has {len(tool_outputs[tool_name])} items)")
                                break  # Move to next item once we've matched a tool
                        else:
                            logger.info(f"Tool '{tool_name}' not found in item tool_name")
                else:
                    logger.info("No tool call found in plan")
            else:
                logger.info("No plan found in tool_args")

        # Filter out tools with no cached results
        tools_with_cache = {name: outputs for name, outputs in tool_outputs.items() if outputs}

        # Combine all tool outputs into a single list
        filtered = []
        for tool_name, outputs in tools_with_cache.items():
            filtered.extend(outputs)

        # Log only the tools that actually have cached results
        logger.info(f"Retrieved {len(filtered)} tool outputs from cache for tools: {list(tools_with_cache.keys())}")
        logger.info(f"Now filtering results by input params: {input_params}")

        if input_params:
            results = self._filter_results_by_input_params(filtered, input_params)
            return results
        else:
            return filtered

    def _filter_results_by_input_params(self, results: List[Dict], input_params: dict) -> List[Dict]:
        """
        Filter cached results based on input parameters extracted from the plan.
        
        Args:
            results: List of cached results to filter
            input_params: Input parameters to match against
            
        Returns:
            Filtered list of results that match the input parameters
        """
        logger.info(f"[memory] 🔍 Starting input params filtering with {len(results)} results")
        logger.info(f"[memory] 🔍 Input params to match against: {input_params}")
        
        # Dump first result for debugging
        if results:
            logger.info(f"[memory] 🔍 Sample result structure: {results[0]}")
            logger.info(f"[memory] 🔍 Sample result tool_args: {results[0].tool_args}")
            logger.info(f"[memory] 🔍 Sample result plan: {results[0].tool_args.get('plan', '') if isinstance(results[0].tool_args, dict) else 'No plan'}")
        
        if not input_params:
            logger.info("[memory] 🔍 No input params provided, returning all results")
            return results
        
        filtered_results = []
        for idx, result in enumerate(results):
            logger.info(f"[memory] 🔍 Processing result {idx}")
            logger.info(f"[memory] 🔍 Processing result value: {str(result.__dict__)[:200]}...")
            
            # Extract plan from tool_args if it exists
            plan = result.tool_args.get('plan', '') if isinstance(result.tool_args, dict) else ''
            if not plan:
                logger.info(f"[memory] 🔍 Result {idx} has no plan, skipping")
                continue
            
            logger.info(f"[memory] 🔍 Result {idx} plan content: {plan}")
            
            # Extract input parameters from the plan
            plan_input_params = {}
            try:
                # Look for input = {...} pattern in the plan
                input_lines = [line for line in plan.split('\n') if 'input = {' in line]
                logger.info(f"[memory] 🔍 Found {len(input_lines)} input lines in plan")
                
                if input_lines:
                    # Get the last input definition (most recent)
                    input_str = input_lines[-1].split('input = ')[1].strip()
                    logger.info(f"[memory] 🔍 Extracted input string: {input_str}")
                    
                    # Convert string representation to dict
                    plan_input_params = eval(input_str)
                    logger.info(f"[memory] 🔍 Extracted plan input params: {plan_input_params}")
            except Exception as e:
                logger.warning(f"[memory] 🔍 Failed to extract input params from plan: {e}")
                continue
            
            # Check if the input parameters match
            if self._do_input_params_match(plan_input_params, input_params):
                logger.info(f"[memory] 🔍 Result {idx} matched input params")
                filtered_results.append(result)
            else:
                logger.info(f"[memory] 🔍 Result {idx} did not match input params")
            
        logger.info(f"[memory] 🔍 Filtered to {len(filtered_results)} matching results")
        return filtered_results

    def _do_input_params_match(self, plan_params: dict, target_params: dict) -> bool:
        """
        Check if the input parameters from plan match the target parameters.
        Uses fuzzy matching for string parameters and exact matching for others.
        
        Args:
            plan_params: Input parameters extracted from plan
            target_params: Target parameters to match against
            
        Returns:
            True if parameters match, False otherwise
        """
        logger.info(f"[memory] 🔍 Starting parameter matching")
        logger.info(f"[memory] 🔍 Plan params: {plan_params}")
        logger.info(f"[memory] 🔍 Target params: {target_params}")
        
        if not plan_params or not target_params:
            logger.info("[memory] 🔍 Missing plan or target params")
            return False
        
        # Extract the actual input parameters from the nested structure
        plan_input = plan_params.get('input', {})
        target_input = target_params.get('input', {})
        
        logger.info(f"[memory] 🔍 Plan input: {plan_input}")
        logger.info(f"[memory] 🔍 Target input: {target_input}")
        
        # Check if all keys in target_input exist in plan_input
        for key, value in target_input.items():
            logger.info(f"[memory] 🔍 Checking key: {key}")
            if key not in plan_input:
                logger.info(f"[memory] 🔍 Key {key} not found in plan input")
                return False
            
            plan_value = plan_input[key]
            logger.info(f"[memory] 🔍 Comparing values - Plan: {plan_value}, Target: {value}")
            
            # Special handling for string parameters
            if isinstance(value, str) and isinstance(plan_value, str):
                # Convert both to lowercase for case-insensitive comparison
                value = value.lower()
                plan_value = plan_value.lower()
                
                # Use fuzzy matching with a threshold of 80
                similarity = fuzz.ratio(value, plan_value)
                logger.info(f"[memory] 🔍 String comparison for key {key}: similarity={similarity}%")
                
                if similarity < 80:
                    logger.info(f"[memory] 🔍 String similarity below threshold for key {key}")
                    return False
            # Exact matching for non-string values
            elif plan_value != value:
                logger.info(f"[memory] 🔍 Non-string values don't match for key {key}")
                return False
            
        logger.info("[memory] 🔍 All parameters matched successfully")
        return True
