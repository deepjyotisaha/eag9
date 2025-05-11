# modules/memory.py

import json
import os
import time
import yaml
import re
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from config.log_config import setup_logging
import difflib

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
        logger.info(f"Loading memory from {self.memory_path}")
        if os.path.exists(self.memory_path):
            with open(self.memory_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.items = [MemoryItem(**item) for item in raw]
                logger.info(f"Loaded {len(self.items)} items from {self.memory_path}")
        else:
            logger.info(f"Memory file does not exist at {self.memory_path}")
            self.items = []

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
    
    def get_tool_results_from_cache(self, selected_tools=None):
        """
        Returns a list of the last N tool outputs from cached memory for the selected tools,
        where N is the lookback_days configured in profiles.yaml.
        If selected_tools is None, returns None.
        """
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
        logger.debug(f"Initialized tool_outputs tracking for: {list(tool_outputs.keys())}")

        # Process items in chronological order (newest first)
        for item in all_items:
            if item.type != "tool_output":
                continue

            # Log each tool_output item we're processing
            logger.debug(f"Processing tool_output item: {item.__dict__}")
            
            # Extract actual tool name from tool_args.plan
            if hasattr(item, 'tool_args') and isinstance(item.tool_args, dict) and 'plan' in item.tool_args:
                plan = item.tool_args['plan']
                # Look for mcp.call_tool('tool_name', input) pattern
                import re
                tool_call_match = re.search(r"await\s+mcp\.call_tool\s*\(\s*['\"]([^'\"]+)['\"]", plan)
                if tool_call_match:
                    actual_tool_name = tool_call_match.group(1)
                    logger.debug(f"Extracted actual tool name from plan: {actual_tool_name}")
                    
                    # Check if this item is for one of our selected tools
                    for tool_name in tool_names:
                        if actual_tool_name == tool_name:
                            logger.debug(f"Found match for tool '{tool_name}' in item")
                            # If we haven't collected N outputs for this tool yet, add it
                            if len(tool_outputs[tool_name]) < lookback_tool_results:
                                tool_outputs[tool_name].append(item)
                                logger.debug(f"Added item to outputs for '{tool_name}' (now has {len(tool_outputs[tool_name])} items)")
                                break  # Move to next item once we've matched a tool
                        else:
                            logger.debug(f"Tool '{tool_name}' not found in item tool_name")
                else:
                    logger.debug("No tool call found in plan")
            else:
                logger.debug("No plan found in tool_args")

        # Filter out tools with no cached results
        tools_with_cache = {name: outputs for name, outputs in tool_outputs.items() if outputs}

        # Combine all tool outputs into a single list
        filtered = []
        for tool_name, outputs in tools_with_cache.items():
            filtered.extend(outputs)

        # Log only the tools that actually have cached results
        logger.info(f"Retrieved {len(filtered)} tool outputs from cache for tools: {list(tools_with_cache.keys())}")
        return filtered
