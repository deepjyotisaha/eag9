from typing import List, Optional
from modules.perception import PerceptionResult
from modules.memory import MemoryItem
from modules.model_manager import ModelManager
from modules.tools import load_prompt
import re
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



model = ModelManager()


# prompt_path = "prompts/decision_prompt.txt"

async def generate_plan(
    user_input: str, 
    perception: PerceptionResult,
    memory_items: List[MemoryItem],
    tool_descriptions: Optional[str],
    tool_output_from_cache: Optional[str],
    prompt_path: str,
    step_num: int = 1,
    max_steps: int = 3,
    lifelines_left: int = 3,
) -> str:

    """Generates the full solve() function plan for the agent."""

    #memory_texts = "\n".join(f"- {m.text}" for m in memory_items) or "None"
    #memory_texts = context.format_history_for_llm() if context.tool_calls else "No previous actions"
    memory_texts = memory_items

    #logger.info(f"Memory texts: {memory_texts} \n\n")

    prompt_path = "prompts/decision_prompt_conservative_optimized.txt"

    logger.info(f"Prompt path: {prompt_path}")

    prompt_template = load_prompt(prompt_path)

    perception_str = str(perception)

    prompt = prompt_template.format(
        user_input=user_input,
        tool_descriptions=tool_descriptions,
        memory_texts=memory_texts,
        perception=perception_str,
        step_num=step_num,
        max_steps=max_steps,
        lifelines_left=lifelines_left
    )

    #logger.info(f"Seeking plan for user input: {user_input}\n with prompt: {prompt}")

    try:
        raw = (await model.generate_text(prompt)).strip()
        logger.info(f"LLM output: {raw}")

        # If fenced in ```python ... ```, extract
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.lower().startswith("python"):
                raw = raw[len("python"):].strip()

        if re.search(r"^\s*(async\s+)?def\s+solve\s*\(", raw, re.MULTILINE):
            return raw  # ✅ Correct, it's a full function
        else:
            logger.error("plan", "⚠️ LLM did not return a valid solve(). Defaulting to FINAL_ANSWER")
            return "FINAL_ANSWER: [Could not generate valid solve()]"


    except Exception as e:
        logger.error("plan", f"⚠️ Planning failed: {e}")
        return "FINAL_ANSWER: [unknown]"
