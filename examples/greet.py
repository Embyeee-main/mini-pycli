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
