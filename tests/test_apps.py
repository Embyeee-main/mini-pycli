import pytest

from mini_pycli.app import App
from mini_pycli.core_nodes import LoopingNode, SingleNode
from mini_pycli.data import BaseState, NodeReturnValue, SpecialReturnValue


class State(BaseState):
    def __init__(self, monkeypatch) -> None:
        super().__init__()
        self.monkeypatch = monkeypatch


def init_test(monkeypatch) -> State:
    return State(monkeypatch)


def update_test(test) -> None:
    print("update")


def exit_test(test) -> None:
    print("exit")


@pytest.fixture
def app(monkeypatch) -> App:
    test_app = App(init_test, update_test, exit_test)
    test_app.init(monkeypatch=monkeypatch)
    return test_app


def exit_cb_test(state) -> NodeReturnValue:
    return NodeReturnValue("test2")


def input_parse_test(_in: str, state):
    if _in not in ["quit", "input_test"]:
        return SpecialReturnValue.INVALID_INPUT
    return _in


def on_invalid_test(val, state) -> None:
    raise ValueError()


def init_cb_test(state) -> None:
    pass


@pytest.fixture
def single_node() -> SingleNode:
    return SingleNode(
        "test",
        "type anything",
        exit_cb_test,
        on_invalid_test,
        init_cb_test,
        input_parse_test,
    )


def quit_callback(val, state) -> bool:
    if val == "quit":
        state.running = False
        return True
    else:
        return False


def loop_callback(val, vals, state: State) -> None:
    state.monkeypatch.setattr("builtins.input", lambda _: "quit")


@pytest.fixture
def looping_node() -> LoopingNode:
    return LoopingNode(
        "test2",
        "type anything",
        quit_callback,
        exit_cb_test,
        on_invalid_test,
        init_cb_test,
        input_parse_test,
        loop_callback,
    )


def test_add_node(app, single_node, looping_node) -> None:
    app.add_node(single_node)
    app.add_node(looping_node)

    assert app.node_exists("test")
    assert app.node_exists("test2")

    try:
        app.add_node(single_node)
    except Exception as e:
        assert isinstance(e, ValueError)


def test_remove_node(app, single_node, looping_node) -> None:
    app.add_node(single_node)
    app.add_node(looping_node)

    app.remove_node("test")
    app.remove_node("test2")

    assert not app.node_exists("test")
    assert not app.node_exists("test2")


def test_set_current_node(app, looping_node) -> None:
    app.add_node(looping_node)
    app.set_current_node("test2")

    assert app.node_stack[-1] == "test2"
    assert not app.set_current_node("fail")


def test_get_current_node(app, single_node) -> None:
    app.add_node(single_node)
    app.set_current_node("test")
    print(app.node_stack)

    assert app.get_current_node() == single_node


def test_set_node_to_last_node(app, single_node, looping_node) -> None:
    app.add_node(single_node)
    app.add_node(looping_node)

    app.set_current_node("test")
    app.set_current_node("test2")

    app._set_current_node_last_in_stack()

    assert app.get_current_node() == single_node
    assert not app._set_current_node_last_in_stack()


def test_set_node_to_next_node(app, single_node, looping_node) -> None:
    app.add_node(single_node)
    app.add_node(looping_node)

    app.set_current_node("test")
    app.set_current_node("test2")

    app._set_current_node_last_in_stack()
    app._set_current_node_next_in_stack()

    assert app.get_current_node() == looping_node
    assert not app._set_current_node_next_in_stack()


def test_mainloop(monkeypatch, capsys, app, single_node, looping_node) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "input_test")

    app.add_node(single_node)
    app.add_node(looping_node)

    app.set_current_node("test")
    app.set_current_node("test2")

    app._set_current_node_last_in_stack()

    assert app.get_current_node().name == "test"

    app.mainloop()

    captured = capsys.readouterr()
    assert captured.out == "update\nupdate\nexit\n"


