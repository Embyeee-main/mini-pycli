from dataclasses import dataclass

from mini_pycli.app import App
from mini_pycli.core_nodes import (LoopingNode, NodeOutput, NodeReturnValue,
                                   SingleNode, SpecialReturnValue)


# 1. Define the shared state. It must be a regular object with a __dict__
#    (a dataclass or SimpleNamespace works).
@dataclass
class State:
    greeting: str


# called when the app.init() is called and must return a state object
def init_callback(greeting: str) -> State:
    return State(greeting)


# update is called after every node finishes
def update_callback(state: State) -> None:
    if state.cur_node == "items":
        prev_item_outputs: NodeOutput = state.prev_outputs["items"]
        print("Current list: " + ", ".join(prev_item_outputs.previous_outputs))


# 2. Create the app. init_callback builds your state object.
app = App(init_callback=init_callback, update_callback=update_callback)
app.init(greeting="Hello")  # extra kwargs are forwarded to init_callback


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
    # drop "done"
    entered = state.prev_outputs["items"].most_recent_output[:-1]
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
