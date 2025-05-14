# EAG9 - Enhanced AI Agent System

## Overview
EAG9 is an advanced AI agent system that implements a robust perception-decision-action loop with sophisticated memory management and tool execution capabilities. The system is designed to handle complex tasks through a modular architecture that emphasizes reliability, extensibility, and intelligent decision-making.

## System Architecture

### 1. Core Components

#### Agent Loop (`core/loop.py`)
- Manages the main execution cycle
- Coordinates between perception, decision, and action modules
- Handles input validation and error recovery
- Implements retry mechanisms with lifelines

#### Perception Module (`modules/perception.py`)
- Analyzes user input and context
- Identifies relevant tools and servers
- Generates memory lookup queries
- Provides context for decision-making

#### Decision Module (`modules/decision.py`)
- Generates execution plans based on available tools
- Implements different planning strategies:
  - Conservative: Single-step execution
  - Exploratory: Parallel or sequential execution
- Uses configurable prompts for different scenarios

#### Action Module (`modules/action.py`)
- Executes tools in a sandboxed environment
- Handles tool results and error cases
- Implements retry mechanisms
- Processes and validates outputs

### 2. Memory System (`modules/memory.py`)

#### Memory Manager
- Hierarchical storage structure:
  ```
  memory/
    YYYY/
      MM/
        DD/
          session-{id}.json
  ```
- Session-based memory management
- Memory persistence and retrieval
- Cache system for tool results

#### Cache Features
- Time-to-live (TTL) for cache entries
- Success/failure tracking
- Tag-based organization
- Automatic cleanup of expired entries

### 3. Tool Management

#### MCP Servers
- `mcp_server_1.py`: Math operations
  - Basic arithmetic (add, subtract, multiply, divide)
  - Advanced math (power, cbrt, factorial)
  - Trigonometric functions (sin, cos, tan)
  - Special operations (fibonacci, string conversions)

- `mcp_server_2.py`: Document processing
  - Document search
  - Webpage to markdown conversion
  - PDF extraction

- `mcp_server_3.py`: Web operations
  - DuckDuckGo search
  - HTML download and processing

#### Tool Validation
- Input validation
- URL validation and reachability checks
- Output validation
- File handling validation

### 4. Configuration System

#### Profiles (`config/profiles.yaml`)
```yaml
agent:
  strategy:
    planning_mode: "conservative"  # or "exploratory"
    exploration_mode: "sequential" # or "parallel"
    max_steps: 3
    max_lifelines_per_step: 3

memory:
  lookback_days: 7
  storage:
    base_dir: "memory"
  lookback_tool_results: 2
```

#### Prompts (`prompts/`)
- `decision_prompt_conservative.txt`
- `decision_prompt_exploratory_parallel.txt`
- `decision_prompt_exploratory_sequential.txt`

## Usage

### Basic Usage
```python
from agent import Agent

agent = Agent()
result = await agent.run("Your query here")
```

### Tool Execution Example
```python
# Math operation
result = await agent.run("calculate 2 + 2")

# Web search
result = await agent.run("search for python programming")

# Document processing
result = await agent.run("convert webpage to markdown")
```

### Memory Management
```python
# Access session memory
memory_items = agent.context.memory.get_session_items()

# Add tool output to memory
agent.context.memory.add_tool_output(
    tool_name="example_tool",
    tool_args={"param": "value"},
    tool_result={"result": "data"},
    success=True,
    tags=["example"]
)
```

## Project Structure
```
eag9/
├── agent.py                 # Main agent entry point
├── models.py               # Model definitions
├── pyproject.toml          # Project dependencies
├── validation_rules.md     # Validation documentation
├── bug-report.md          # Bug tracking
│
├── config/                 # Configuration
│   └── profiles.yaml      # Agent settings
│
├── core/                   # Core components
│   ├── loop.py            # Main agent loop
│   ├── strategy.py        # Decision strategies
│   └── context.py         # Context management
│
├── modules/               # Functional modules
│   ├── perception.py      # Input analysis
│   ├── decision.py        # Decision making
│   ├── action.py          # Tool execution
│   ├── memory.py          # Memory management
│   ├── validator.py       # Validation
│   └── tools.py           # Tool utilities
│
├── prompts/               # LLM prompts
│   ├── decision_prompt_conservative.txt
│   ├── decision_prompt_exploratory_parallel.txt
│   └── decision_prompt_exploratory_sequential.txt
│
├── memory/                # Memory storage
│   └── YYYY/MM/DD/       # Hierarchical storage
│
├── logs/                  # System logs
│
├── mcp_server_1.py       # Math operations
├── mcp_server_2.py       # Document processing
├── mcp_server_3.py       # Web operations
└── mcp_server_check.py   # Server health check
```

## Error Handling

### Input Validation
- URL format validation
- URL reachability checks
- File path validation
- Content filtering

### Tool Execution
- Sandboxed execution
- Error recovery
- Cache fallback
- Retry mechanisms

### Memory Management
- Automatic cleanup
- Error logging
- Cache invalidation
- Session management

## Best Practices

### 1. Tool Usage
- Always validate input before tool execution
- Use appropriate error handling
- Implement proper cleanup
- Monitor tool performance

### 2. Memory Management
- Use appropriate tags
- Implement cleanup strategies
- Monitor memory usage
- Use cache effectively

### 3. Error Handling
- Implement proper validation
- Use retry mechanisms
- Log errors appropriately
- Provide meaningful error messages

## Contributing
1. Fork the repository
2. Create a feature branch
3. Implement changes
4. Add tests
5. Submit pull request

## License
[Your License Here]