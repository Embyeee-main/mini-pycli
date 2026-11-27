# mini-pycli

A tiny framework for building interactive, prompt-driven command-line programs out of **nodes**.

Each node asks the user for input, validates and parses it, records the answer, and then decides which node runs next. An `App` runs the nodes in a loop and carries one shared `state` object between them.

- Describe a flow as a set of named nodes (`SingleNode`, `LoopingNode`)
- Validate and parse input per node, with a hook for invalid input
- Branch by returning the name of the next node, or step back and forward through history
- Every answer is stored in `state.prev_outputs`, so later nodes can read earlier answers
- No dependencies beyond the Python standard library (plus pytest for development)

## Requirements

Python **3.13+**

## Installation

The recommended way to set up and use mini-pycli is [uv](https://docs.astral.sh/uv/).

### Add it to a uv project (recommended)

```bash
uv init my-app        # skip if you already have a project
cd my-app
uv add git+https://github.com/Embyeee-main/mini-pycli.git
```

Run your script inside the managed environment:

```bash
uv run main.py
```

### Using pip instead

```bash
# from a local clone
pip install .
# or directly from Git
pip install git+https://github.com/Embyeee-main/mini-pycli.git
```

## Quick start

A complete program with one node:

```python
from mini_pycli.app import App
from mini_pycli.core_nodes import SingleNode
from mini_pycli.data import BaseState, NodeReturnValue, SpecialReturnValue


def make_state() -> BaseState:
    return BaseState()


def say_hello(state: BaseState) -> NodeReturnValue:
    name = state.prev_outputs["greet"].most_recent_output
    print(f"Hello, {name}!")
    state.running = False  # ends the main loop
    return NodeReturnValue(SpecialReturnValue.NEXT_NODE)


greet = SingleNode(
    name="greet",
    prompt="What's your name? ",
    on_invalid=lambda text, state: None,
    exit_callback=say_hello,
)

app = App(init_callback=make_state)
app.init()
app.add_node(greet)
app.set_current_node("greet")
app.mainloop()
```

## How it works

1. You build an `App` with an `init_callback` that creates your state object, then call `app.init(...)`.
2. You register nodes with `add_node` and pick a starting node with `set_current_node`.
3. `mainloop()` repeats the following until `state.running` is `False`:
   1. Set `state.cur_node` to the current node's name.
   2. Run the node: `init_callback` → prompt and parse (re-prompting through `on_invalid` on bad input) → record the answer in `state.prev_outputs` → `exit_callback`.
   3. Navigate to the node named by the returned `NodeReturnValue`.
   4. Call the app's `update_callback(state)`, if any.
4. When the loop ends, the app's `exit_callback(state)` runs, if any.

Two things worth knowing up front:

- **Every node blocks on `input()`.** A node always prompts at least once; there is no "silent" node.
- **Navigation still happens on the final iteration.** A node that sets `state.running = False` must still return a valid `next_node`. `SpecialReturnValue.NEXT_NODE` is always safe.

## Detailed example: a pizza order

This example uses almost every feature of the library:

- a custom state class built on `BaseState`
- a `SingleNode` with validation, using `InputChecker` and `Range`
- a `LoopingNode` with `loop_callback`, `quit_callback`, and `init_callback`
- dynamic prompts built from earlier answers
- branching by node name (`"no"` restarts the order)
- a "back" command using `SpecialReturnValue.LAST_NODE`
- the app-level `update_callback` and `exit_callback`

The flow is:

```
customer ──► pizzas ──► tip ──► confirm ──► receipt
               ▲                   │
               └────── "no" ───────┘      ("back" steps one node back from tip and confirm)
```

Save this as `main.py`:

```python
from mini_pycli.app import App
from mini_pycli.core_nodes import LoopingNode, SingleNode
from mini_pycli.data import BaseState, NodeReturnValue, SpecialReturnValue
from mini_pycli.utils import InputChecker, Range

PRICES = {"margherita": 9.0, "pepperoni": 11.0, "veggie": 10.0}


# --------------------------------------------------------------------------
# 1. State. It must inherit from BaseState, which provides `running`,
#    `prev_outputs` and `cur_node`. Call super().__init__() in your __init__.
# --------------------------------------------------------------------------
class OrderState(BaseState):
    def __init__(self, shop_name: str) -> None:
        super().__init__()
        self.shop_name = shop_name
        self.subtotal = 0.0
        self.trail: list[str] = []  # names of the nodes we have finished


def make_state(shop_name: str) -> OrderState:
    """App.init(shop_name=...) forwards its keyword arguments to this function."""
    return OrderState(shop_name)


def total_with_tip(state: OrderState) -> float:
    tip_percent = state.prev_outputs["tip"].most_recent_output
    return state.subtotal * (1 + tip_percent / 100)


# --------------------------------------------------------------------------
# 2. Parsing helpers. A parser returns the parsed value, or
#    SpecialReturnValue.INVALID_INPUT to reject the input.
#    Any other value (even None) is accepted and stored.
# --------------------------------------------------------------------------
def to_int(text: str):
    """The converter InputChecker uses. It must return INVALID_INPUT, not raise."""
    try:
        return int(text)
    except ValueError:
        return SpecialReturnValue.INVALID_INPUT


def with_back(parser):
    """Wrap a parser so that typing 'back' is accepted as the LAST_NODE sentinel.

    The sentinel is stored as the node's output, and the node's exit callback
    turns it into a navigation request (see go_back_or).
    """

    def wrapped(text, state):
        if text.strip().lower() == "back":
            return SpecialReturnValue.LAST_NODE
        return parser(text, state)

    return wrapped


def go_back_or(next_node: str):
    """Build an exit_callback that goes back if the user typed 'back'."""

    def exit_callback(state: OrderState) -> NodeReturnValue:
        answer = state.prev_outputs[state.cur_node].most_recent_output
        if answer is SpecialReturnValue.LAST_NODE:
            return NodeReturnValue(SpecialReturnValue.LAST_NODE)
        return NodeReturnValue(next_node)

    return exit_callback


# --------------------------------------------------------------------------
# 3. Node: customer (SingleNode)
# --------------------------------------------------------------------------
def parse_customer(text: str, state: OrderState):
    name = text.strip()
    return name or SpecialReturnValue.INVALID_INPUT  # empty names are rejected


customer = SingleNode(
    name="customer",
    prompt=lambda state: f"Welcome to {state.shop_name}! Your name? ",  # dynamic prompt
    input_parser=parse_customer,
    on_invalid=lambda text, state: print("Please enter a name."),
    exit_callback=lambda state: NodeReturnValue("pizzas"),  # jump by node name
)


# --------------------------------------------------------------------------
# 4. Node: pizzas (LoopingNode)
#    Collects answers until quit_callback returns True. The stored output is
#    the whole list, including the final "done".
# --------------------------------------------------------------------------
def start_pizzas(state: OrderState) -> None:
    """init_callback: runs once each time the node starts, before the first prompt."""
    state.subtotal = 0.0  # a fresh order every time we enter this node
    menu = ", ".join(f"{name} (${price:.2f})" for name, price in PRICES.items())
    print(f"Menu: {menu}")


def parse_pizza(text: str, state: OrderState):
    choice = text.strip().lower()
    if choice in PRICES or choice == "done":
        return choice
    return SpecialReturnValue.INVALID_INPUT


def on_pizza(choice: str, buffer: list[str], state: OrderState) -> None:
    """loop_callback: runs after every valid answer, before quit_callback."""
    if choice == "done":
        if state.subtotal == 0:
            print("Add at least one pizza first.")
        return
    state.subtotal += PRICES[choice]
    print(f"  added {choice}; subtotal ${state.subtotal:.2f}")


pizzas = LoopingNode(
    name="pizzas",
    prompt="Pick a pizza (or 'done'): ",
    input_parser=parse_pizza,
    on_invalid=lambda text, state: print(f"Not on the menu: {text.strip()!r}"),
    init_callback=start_pizzas,
    loop_callback=on_pizza,
    # Stop only when the user says "done" and has ordered something.
    quit_callback=lambda choice, state: choice == "done" and state.subtotal > 0,
    exit_callback=lambda state: NodeReturnValue("tip"),
)


# --------------------------------------------------------------------------
# 5. Node: tip (SingleNode with InputChecker)
# --------------------------------------------------------------------------
tip_checker = InputChecker(_type=to_int, _range=Range(0, 30))


def parse_tip(text: str, state: OrderState):
    # check() returns True, False, or INVALID_INPUT. `is True` handles all three.
    if tip_checker.check(text) is True:
        return to_int(text)
    return SpecialReturnValue.INVALID_INPUT


tip = SingleNode(
    name="tip",
    prompt="Tip percent (0-30, or 'back'): ",
    input_parser=with_back(parse_tip),
    on_invalid=lambda text, state: print("Enter a whole number from 0 to 30."),
    exit_callback=go_back_or("confirm"),
)


# --------------------------------------------------------------------------
# 6. Node: confirm. Branches three ways: forward, back, or restart.
# --------------------------------------------------------------------------
def parse_confirm(text: str, state: OrderState):
    answer = text.strip().lower()
    return answer if answer in ("yes", "no") else SpecialReturnValue.INVALID_INPUT


def confirm_exit(state: OrderState) -> NodeReturnValue:
    answer = state.prev_outputs["confirm"].most_recent_output
    if answer is SpecialReturnValue.LAST_NODE:
        return NodeReturnValue(SpecialReturnValue.LAST_NODE)  # back to "tip"
    if answer == "yes":
        return NodeReturnValue("receipt")
    return NodeReturnValue("pizzas")  # "no": start the order over


confirm = SingleNode(
    name="confirm",
    prompt=lambda state: (
        f"Total with tip is ${total_with_tip(state):.2f}. "
        "Place order? (yes/no/back) "
    ),
    input_parser=with_back(parse_confirm),
    on_invalid=lambda text, state: print("Please answer yes, no, or back."),
    exit_callback=confirm_exit,
)


# --------------------------------------------------------------------------
# 7. Node: receipt. Prints the summary and ends the program.
# --------------------------------------------------------------------------
def finish(state: OrderState) -> NodeReturnValue:
    name = state.prev_outputs["customer"].most_recent_output
    # The looping node stores its whole buffer; drop the trailing "done".
    ordered = state.prev_outputs["pizzas"].most_recent_output[:-1]
    print(f"Thanks, {name}! {len(ordered)} pizza(s): {', '.join(ordered)}")
    print(f"Charged ${total_with_tip(state):.2f}")

    state.running = False  # tells mainloop to stop after this iteration
    return NodeReturnValue(SpecialReturnValue.NEXT_NODE)  # still must be valid


receipt = SingleNode(
    name="receipt",
    prompt="Press enter to print your receipt. ",
    on_invalid=lambda text, state: None,  # required, but raw input is never invalid
    exit_callback=finish,
)


# --------------------------------------------------------------------------
# 8. App-level callbacks
# --------------------------------------------------------------------------
def update(state: OrderState) -> None:
    """Runs after every node. state.cur_node is the node that just finished."""
    state.trail.append(state.cur_node)


def goodbye(state: OrderState) -> None:
    """Runs once, after the main loop ends."""
    print(f"Visited: {' -> '.join(state.trail)}")
    print(f"Goodbye from {state.shop_name}!")


# --------------------------------------------------------------------------
# 9. Wire it together and run
# --------------------------------------------------------------------------
def main() -> None:
    app = App(init_callback=make_state, update_callback=update, exit_callback=goodbye)
    app.init(shop_name="Pie Hard")  # kwargs are forwarded to make_state

    for node in (customer, pizzas, tip, confirm, receipt):
        app.add_node(node)

    app.set_current_node("customer")  # the starting node
    app.mainloop()


if __name__ == "__main__":
    main()
```

A sample session:

```
Welcome to Pie Hard! Your name? Ada
Menu: margherita ($9.00), pepperoni ($11.00), veggie ($10.00)
Pick a pizza (or 'done'): pepperoni
  added pepperoni; subtotal $11.00
Pick a pizza (or 'done'): pineapple
Not on the menu: 'pineapple'
Pick a pizza (or 'done'): veggie
  added veggie; subtotal $21.00
Pick a pizza (or 'done'): done
Tip percent (0-30, or 'back'): 15
Total with tip is $24.15. Place order? (yes/no/back) yes
Press enter to print your receipt.
Thanks, Ada! 2 pizza(s): pepperoni, veggie
Charged $24.15
Visited: customer -> pizzas -> tip -> confirm -> receipt
Goodbye from Pie Hard!
```

Answering `no` at the confirmation sends the user back to `pizzas`. The earlier order is not lost: it moves to `state.prev_outputs["pizzas"].previous_outputs`, while the new order becomes `most_recent_output`.

## Reference

### `App`

```python
from mini_pycli.app import App

App(init_callback, update_callback=None, exit_callback=None)
```

| Parameter | Description |
| --- | --- |
| `init_callback` | `(**kwargs) -> BaseState`. Called by `init()`; must return an instance of a `BaseState` subclass. |
| `update_callback` | Optional `(state) -> None`. Runs after every node finishes and navigation is applied. `state.cur_node` is still the node that just finished. |
| `exit_callback` | Optional `(state) -> None`. Runs once after the main loop ends. |

| Method | Description |
| --- | --- |
| `init(**kwargs)` | Calls `init_callback(**kwargs)` and stores the state. Raises `TypeError` if the state does not inherit from `BaseState`. **Call this before anything else.** |
| `add_node(node)` | Registers a node and creates its `NodeOutput`. Names must be unique (`ValueError` otherwise). |
| `remove_node(name)` | Unregisters a node. Its recorded outputs and any stack entries are left in place. |
| `node_exists(name)` | `True` if a node with that name is registered. |
| `set_current_node(name)` | Pushes the named node onto the node stack and makes it current. Use this to choose the start node. Returns `False` if the name is unknown. |
| `get_current_node()` | Returns the node the stack currently points at. |
| `mainloop()` | Runs nodes until `state.running` becomes `False`. |

### State: `BaseState`

Your state class must inherit from `BaseState`. It provides:

- `state.running`: set it to `False` (typically from an `exit_callback`) to stop `mainloop`.
- `state.prev_outputs`: a dict mapping each node name to a `NodeOutput`.
- `state.cur_node`: the name of the node most recently started by the main loop.

If you subclass with `@dataclass`, the generated `__init__` replaces `BaseState.__init__`, so call it yourself:

```python
@dataclass
class State(BaseState):
    shop_name: str

    def __post_init__(self) -> None:
        super().__init__()
```

### `NodeOutput`

The history of values one node has produced.

- `most_recent_output`: the latest value (`None` until the node has run).
- `previous_outputs`: earlier values, oldest first.

For a `SingleNode` each value is the parsed input. For a `LoopingNode` each value is the list collected during one run of the node, so `previous_outputs` is a list of lists.

### `SingleNode`

Asks once (re-asking until the input is valid), stores the parsed value, then calls `exit_callback`.

```python
SingleNode(
    name,                 # unique node name
    prompt,               # str, or callable(state) -> str
    exit_callback,        # callable(state) -> NodeReturnValue
    on_invalid,           # callable(raw_text, state) -> None
    init_callback=None,   # optional callable(state); runs before the first prompt
    input_parser=None,    # optional callable(raw_text, state) -> parsed value | INVALID_INPUT
)
```

- If `input_parser` is omitted, the raw string is stored.
- If `input_parser` returns `SpecialReturnValue.INVALID_INPUT`, `on_invalid` is called and the prompt repeats. Any other return value, including `None`, is accepted as the answer.

### `LoopingNode`

Keeps prompting and collects every valid answer into a list. When the loop ends, the whole list is stored as the node's output.

```python
LoopingNode(
    name,
    prompt,
    quit_callback,        # callable(parsed_value, state) -> bool
    exit_callback,
    on_invalid,
    init_callback=None,
    input_parser=None,
    loop_callback=None,   # callable(parsed_value, buffer, state) -> None
)
```

- After each valid answer, `loop_callback` runs (if given), then `quit_callback` is checked. **Return `True` to stop; return `False` to keep asking.**
- The answer that causes the loop to stop is included in the stored list.
- Rejected inputs are never added to the list and never reach `quit_callback`.
- `init_callback` runs once when the node starts, not once per answer.

### Controlling the flow: `NodeReturnValue` and `SpecialReturnValue`

Every node's `exit_callback` returns `NodeReturnValue(next_node=...)`, where `next_node` is one of:

| Value | Effect |
| --- | --- |
| `"some_name"` | Jump to the node with that name. It is pushed onto the end of the history stack. Raises `ValueError` if no such node is registered. |
| `SpecialReturnValue.NEXT_NODE` | Move forward one step in the history stack. |
| `SpecialReturnValue.LAST_NODE` | Move back one step in the history stack (for example, a "go back" option). |

The app keeps a history stack of visited nodes. Jumping by name pushes onto the end of it (history is never truncated); `LAST_NODE` and `NEXT_NODE` move a pointer back and forth through it. Moving past either end does nothing, so the current node simply runs again.

`SpecialReturnValue.INVALID_INPUT` has a different job: return it from an `input_parser` to reject the input.

### Validation helpers: `mini_pycli.utils`

These are optional building blocks for `input_parser` functions.

- **`Range(_min, _max)`**: an inclusive range check for numbers (or `Comparable` subclasses that implement `in_range(_min, _max)`).
- **`InputChecker(_type, _in, not_in, _range, regex)`**: declarative validation of a raw string. Set any combination:
  - `_type`: converter called with the raw string. It must return `SpecialReturnValue.INVALID_INPUT` on failure instead of raising.
  - `_in` / `not_in`: allow-list and deny-list for the raw string.
  - `regex`: a compiled pattern, matched from the start of the string (end it with `$` for a full match).
  - `_range`: a `Range`, checked against the converted value. It requires `_type`.

`checker.check(text)` returns `True` or `False`, or `SpecialReturnValue.INVALID_INPUT` if `_type` could not convert the text. It does not return the converted value, so convert again after a successful check, as the `parse_tip` function in the example does.

## Tips

- Put validation in `input_parser` and the error message in `on_invalid`.
- Use a callable `prompt` to build prompts from earlier answers: `lambda state: f"Hi {state.prev_outputs['greet'].most_recent_output}, ..."`.
- Use a node's `init_callback` to reset or prepare state each time the node is entered.
- To end the program, set `state.running = False` in an `exit_callback` and return `SpecialReturnValue.NEXT_NODE`.
- The parsed value can be any object, including a `SpecialReturnValue`. The example uses this to turn a typed "back" into navigation: store `LAST_NODE` as the answer, then have `exit_callback` return it.
- Use `update_callback` for rendering and bookkeeping that should happen after every node, and `exit_callback` on the app for cleanup.

## Development

```bash
uv sync
uv run pytest
```
