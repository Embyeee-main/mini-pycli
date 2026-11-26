# mini-pycli

A tiny framework for building interactive, prompt-driven command-line programs out of **nodes**. Each node asks the user for input, validates it, stores the result, and then decides which node runs next. An `App` runs the nodes in a loop and carries a shared `state` object between them.

- Define a flow as a set of named nodes (`SingleNode`, `LoopingNode`)
- Validate and parse input per node, with a hook for invalid input
- Branch by returning the name of the next node
- Every answer is stored in `state.prev_outputs`, so later nodes can read earlier answers
- No dependencies beyond the Python standard library

## Requirements

Python **3.10+**

## Installation

The recommended way to set up and use mini-pycli is [uv](https://docs.astral.sh/uv/).

### Add it to a uv project (recommended)

```bash
uv init my-app        # skip if you already have a project
cd my-app
uv add [<repo-url>](https://github.com/Embyeee-main/mini-pycli.git)
```

Run your script inside the managed environment:

```bash
uv run main.py
```

### Using pip instead

```bash
pip install mini-pycli
# or, from a local clone
pip install .
# or, directly from Git
pip install git+[<repo-url>](https://github.com/Embyeee-main/mini-pycli.git)
```

## Quick start

```python
from dataclasses import dataclass

from mini_pycli.app import App
from mini_pycli.core_nodes import (
    LoopingNode,
    NodeReturnValue,
    SingleNode,
    SpecialReturnValue,
)


# 1. Define the shared state. It must be a regular object with a __dict__
#    (a dataclass or SimpleNamespace works).
@dataclass
class State:
    greeting: str = "Hello"


# called when the app.init() is called and must return a state object
def init_callback(**kwargs) -> State:
    return State()


# update is called after every node finishes
def update_callback(state: State) -> None:
    print("hi from the update callback!")


# 2. Create the app. init_callback builds your state object.
app = App(init_callback=init_callback, update_callback=update_callback)
app.init()  # extra kwargs are forwarded to init_callback


# 3. Define nodes.
greet = SingleNode(
    name="greet",
    prompt=lambda state: f"{state.greeting}! What's your name? ",
    input_parser=lambda text, state: text.strip() or None,  # None = invalid
    on_invalid=lambda text, state: print("Name can't be empty."),
    exit_callback=lambda state: NodeReturnValue(next_node="items"),
)

items = LoopingNode(
    name="items",
    prompt="Add an item (type 'done' to finish): ",
    quit_callback=lambda value, state: value == "done",  # True = stop looping
    on_invalid=lambda text, state: None,
    exit_callback=lambda state: NodeReturnValue(next_node="summary"),
)


def finish(state):
    name = state.prev_outputs["greet"].most_recent_output
    entered = state.prev_outputs["items"].most_recent_output[:-1]  # drop "done"
    print(f"{name} added: {', '.join(entered) or 'nothing'}")
    state.running = False  # stops the main loop
    return NodeReturnValue(next_node=SpecialReturnValue.NEXT_NODE)


summary = SingleNode(
    name="summary",
    prompt="Press enter to finish. ",
    on_invalid=lambda text, state: None,
    exit_callback=finish,
)

# 4. Register nodes, pick the starting node, and run.
for node in (greet, items, summary):
    app.add_node(node)

app.set_current_node("greet")
app.mainloop()
```

## Core concepts

### `App`

```python
App(init_callback)
```

| Method | Description |
| --- | --- |
| `init(**kwargs)` | Calls `init_callback(**kwargs)` to build the state. Adds `running = True` and `prev_outputs = {}` to it. **Must be called before anything else.** |
| `add_node(node)` | Registers a node. Names must be unique (`ValueError` otherwise). |
| `remove_node(name)` | Unregisters a node. |
| `node_exists(name)` | `True` if a node with that name is registered. |
| `set_current_node(name)` | Pushes the named node onto the node stack and makes it current. Use this to choose the start node. |
| `get_current_node()` | Returns the node currently at the top of the stack pointer. |
| `mainloop()` | Runs nodes until `state.running` becomes `False`. |

### State

The state is whatever your `init_callback` returns. The app adds two attributes:

- `state.running` – set it to `False` (typically from an `exit_callback`) to stop `mainloop`.
- `state.prev_outputs` – a dict mapping each node name to a `NodeOutput`.

`NodeOutput` has:

- `most_recent_output` – the latest value stored by that node
- `previous_outputs` – a list of earlier values (older runs of the node)

### `SingleNode`

Asks once (re-asking until the input is valid), stores the parsed value, then calls `exit_callback`.

```python
SingleNode(
    name,             # unique node name
    prompt,           # str, or callable(state) -> str
    exit_callback,    # callable(state) -> NodeReturnValue
    on_invalid,       # callable(raw_text, state) -> None
    init_callback=None,   # optional callable(state), runs before prompting
    input_parser=None,    # optional callable(raw_text, state) -> parsed value or None
)
```

- If `input_parser` is omitted, the raw string is stored.
- If `input_parser` returns `None`, the input is treated as invalid: `on_invalid` is called and the prompt repeats.

### `LoopingNode`

Keeps prompting and collects every valid answer into a list. When the loop ends, the whole list is stored as the node's output.

```python
LoopingNode(
    name,
    prompt,
    quit_callback,    # callable(parsed_value, state) -> bool
    exit_callback,
    on_invalid,
    init_callback=None,
    input_parser=None,
    loop_callback=None,   # callable(parsed_value, buffer, state), runs after each answer
)
```

- `quit_callback` is checked after each valid answer. **Return `True` to stop the loop; return `False` to keep asking.**
- The answer that causes the loop to stop is included in the stored list.
- `loop_callback` is optional. If given, it is called after every valid answer.

### Controlling the flow

Every node's `exit_callback` returns a `NodeReturnValue(next_node=...)`, where `next_node` is one of:

| Value | Effect |
| --- | --- |
| `"some_name"` | Jump to the node with that name. |
| `SpecialReturnValue.NEXT_NODE` | Move forward in the node history stack. |
| `SpecialReturnValue.LAST_NODE` | Move back in the node history stack (for example, a "go back" option). |

The app keeps a history stack of visited nodes. Jumping by name pushes onto it; `LAST_NODE` / `NEXT_NODE` move the pointer back and forth through it.

## Tips

- Put validation in `input_parser` and the error message in `on_invalid`.
- Use a callable `prompt` to build prompts from earlier answers: `lambda state: f"Hi {state.prev_outputs['greet'].most_recent_output}, ..."`.
- Use `init_callback` on a node to reset or prepare state each time the node is entered.
- To end the program, set `state.running = False` in an `exit_callback`.
