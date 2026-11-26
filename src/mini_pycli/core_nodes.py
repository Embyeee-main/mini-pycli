from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Generic, Optional, TypeVar, Union

T = TypeVar("T")
U = TypeVar("U")


class SpecialReturnValue(Enum):
    LAST_NODE = auto()
    NEXT_NODE = auto()


class NodeOutput(Generic[T]):
    def __init__(self) -> None:
        self.most_recent_output: T = None
        self.previous_outputs: list[T] = []

    def add_output(self, output: T) -> None:
        if self.most_recent_output is not None:
            self.previous_outputs.append(self.most_recent_output)
        self.most_recent_output = output


@dataclass
class NodeReturnValue:
    next_node: Union[str, SpecialReturnValue]


@dataclass
class Node(Generic[T]):
    name: str
    prompt: Union[Callable[[U], str], str]
    exit_callback: Callable[[U], NodeReturnValue]
    on_invalid: Callable[[str, U], None]
    init_callback: Optional[Callable[[U], None]] = None
    input_parser: Optional[Callable[[str, U], Optional[T]]] = None

    def call(self, state: U) -> NodeReturnValue:
        if self.init_callback is not None:
            self.init_callback(state)

        while True:
            cur_input = input(
                self.prompt(state) if isinstance(
                    self.prompt, Callable) else self.prompt
            )

            parsed_input = (
                self.input_parser(cur_input, state)
                if self.input_parser is not None
                else cur_input
            )

            if parsed_input is not None:
                break

            self.on_invalid(cur_input, state)

        state.prev_outputs[self.name].add_output(parsed_input)
        return self.exit_callback(state)


class SingleNode(Node):
    def __init__(
        self,
        name: str,
        prompt: Union[Callable[[U], str], str],
        exit_callback: Callable[[U], NodeReturnValue],
        on_invalid: Callable[[str, U], None],
        init_callback: Optional[Callable[[U], None]] = None,
        input_parser: Optional[Callable[[str, U], Optional[T]]] = None,
    ) -> None:
        super().__init__(
            name, prompt, exit_callback, on_invalid, init_callback, input_parser
        )


class LoopingNode(Node):
    def __init__(
        self,
        name: str,
        prompt: Union[Callable[[U], str], str],
        quit_callback: Callable[[T, U], bool],
        exit_callback: Callable[[U], NodeReturnValue],
        on_invalid: Callable[[str, U], None],
        init_callback: Optional[Callable[[U], None]] = None,
        input_parser: Optional[Callable[[str, U], Optional[T]]] = None,
        loop_callback: Optional[Callable[[T, list[T], U], None]] = None,
    ) -> None:
        super().__init__(
            name, prompt, exit_callback, on_invalid, init_callback, input_parser
        )
        self.quit_callback = quit_callback
        self.loop_callback = loop_callback

    def call(self, state: U) -> NodeReturnValue:
        if self.init_callback is not None:
            self.init_callback(state)

        buf = []
        while True:
            while True:
                cur_input = input(
                    self.prompt(state)
                    if isinstance(self.prompt, Callable)
                    else self.prompt
                )
                parsed_input = (
                    self.input_parser(cur_input, state)
                    if self.input_parser is not None
                    else cur_input
                )

                if parsed_input is not None:
                    break

                self.on_invalid(cur_input, state)

            buf.append(parsed_input)
            if self.loop_callback is not None:
                self.loop_callback(parsed_input, buf, state)

            if self.quit_callback(parsed_input, state):
                break

        state.prev_outputs[self.name].add_output(buf)
        return self.exit_callback(state)
