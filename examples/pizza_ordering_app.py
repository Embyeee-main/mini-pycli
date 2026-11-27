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
