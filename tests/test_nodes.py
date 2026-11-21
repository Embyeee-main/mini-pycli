from typing import Any

import pytest

from mini_pycli.core_nodes import (LoopingNode, NodeOutput, NodeReturnValue,
                                   SingleNode)


class State:
    def __init__(self, prev_outputs, monkeypatch) -> None:
        self.prev_outputs: dict[str, Any] = prev_outputs
        self.monkeypatch = monkeypatch


@pytest.fixture
def state(monkeypatch) -> State:
    return State({"test": NodeOutput(), "test2": NodeOutput()}, monkeypatch)


def exit_cb_test(state) -> NodeReturnValue:
    print("exit_cb")
    return NodeReturnValue("none")


def input_parse_test(_in: str, state) -> Any:
    if _in not in ["quit", "test"]:
        return None
    print(_in)
    return _in


def on_invalid_test(val, state) -> None:
    raise ValueError()


def init_cb_test(state) -> None:
    print("init_cb")


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
        return False
    else:
        print("continue")
        return True


def loop_callback(val, vals, state: State) -> None:
    print("foo")
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


def test_single_input_node(
    single_node: SingleNode, state: State, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "test")

    test_next_node = single_node.call(state)
    captured = capsys.readouterr()
    assert captured.out == "init_cb\ntest\nexit_cb\n"
    assert state.prev_outputs["test"].most_recent_output == "test"
    assert test_next_node.next_node == "none"


def test_single_input_node_invalid_input(
    single_node: SingleNode, state: State, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "fail")
    try:
        single_node.call(state)
    except Exception as e:
        assert isinstance(e, ValueError)

    captured = capsys.readouterr()
    assert captured.out == "init_cb\n"


def test_looping_input_node(looping_node, state: State, monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "test")
    test_next_node = looping_node.call(state)

    captured = capsys.readouterr()
    assert captured.out == "init_cb\ntest\nfoo\ncontinue\nquit\nfoo\nexit_cb\n"
    assert state.prev_outputs["test2"].most_recent_output == ["test", "quit"]
    assert test_next_node.next_node == "none"


def test_looping_input_node_invalid_input(
    looping_node: LoopingNode, state: State, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "fail")
    try:
        looping_node.call(state)
    except Exception as e:
        assert isinstance(e, ValueError)

    captured = capsys.readouterr()
    assert captured.out == "init_cb\n"
