"""Core node types for mini-pycli.

A mini-pycli program is a graph of *nodes*. Each node prompts the user for
input, validates and parses it, stores the result on the shared application
state, and then tells the :class:`~mini_pycli.app.App` which node to run next.

Two node types are provided:

* :class:`SingleNode` collects a single valid input.
* :class:`LoopingNode` keeps collecting inputs until a quit condition is met.

Nodes are driven by an ``App``, which supplies the shared ``state`` object
passed to every callback. The state must expose a ``prev_outputs`` mapping of
node name to :class:`NodeOutput` (``App`` sets this up automatically).
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Generic, Optional, TypeVar, Union

T = TypeVar("T")
U = TypeVar("U")


class SpecialReturnValue(Enum):
    """Sentinel values a node can return instead of a node name.

    These tell the ``App`` to navigate relative to its node history rather
    than jumping to a node by name.

    Attributes:
        LAST_NODE: Go back to the previous node in the app's node stack.
        NEXT_NODE: Go forward to the next node in the app's node stack.
    """

    LAST_NODE = auto()
    NEXT_NODE = auto()


class NodeOutput(Generic[T]):
    """Stores the history of values a node has produced.

    Each time a node completes, its parsed result is recorded here. The newest
    value is kept in ``most_recent_output`` and older ones are moved to
    ``previous_outputs``, so revisiting a node does not lose earlier answers.

    Attributes:
        most_recent_output: The latest value added, or ``None`` if nothing has
            been added yet.
        previous_outputs: Earlier values, oldest first.
    """

    def __init__(self) -> None:
        """Create an empty output history."""
        self.most_recent_output: T = None
        self.previous_outputs: list[T] = []

    def add_output(self, output: T) -> None:
        """Record a new output.

        The current ``most_recent_output`` (if any) is appended to
        ``previous_outputs`` and ``output`` becomes the new most recent value.

        Args:
            output: The value to record.
        """
        if self.most_recent_output is not None:
            self.previous_outputs.append(self.most_recent_output)
        self.most_recent_output = output


@dataclass
class NodeReturnValue:
    """The result of running a node, telling the app where to go next.

    Attributes:
        next_node: Either the name of the node to run next, or a
            :class:`SpecialReturnValue` to move through the node history.
    """

    next_node: Union[str, SpecialReturnValue]


@dataclass
class Node(Generic[T]):
    """Base class for a prompt-driven step in a CLI flow.

    A node prompts the user, parses the input, stores the result in the shared
    state, and returns a :class:`NodeReturnValue`. Prefer the concrete
    :class:`SingleNode` and :class:`LoopingNode` subclasses.

    Attributes:
        name: Unique name of the node. Used to register it with the app, to
            jump to it from other nodes, and as the key into
            ``state.prev_outputs``.
        prompt: Text shown to the user, or a callable that takes the state and
            returns the text (useful for dynamic prompts).
        exit_callback: Called with the state after the node's input has been
            recorded. Returns a :class:`NodeReturnValue` choosing the next node.
        on_invalid: Called with the raw input and the state whenever
            ``input_parser`` rejects the input (returns ``None``). Typically
            used to print an error message.
        init_callback: Optional. Called with the state once each time the node
            starts, before the first prompt.
        input_parser: Optional. Called with the raw input string and the state.
            Returns the parsed value, or ``None`` to mark the input invalid. If
            omitted, the raw string is used as-is.
    """

    name: str
    prompt: Union[Callable[[U], str], str]
    exit_callback: Callable[[U], NodeReturnValue]
    on_invalid: Callable[[str, U], None]
    init_callback: Optional[Callable[[U], None]] = None
    input_parser: Optional[Callable[[str, U], Optional[T]]] = None

    def call(self, state: U) -> NodeReturnValue:
        """Run the node: prompt until valid input is given, then exit.

        The flow is:

        1. Call ``init_callback(state)`` if provided.
        2. Prompt the user and parse the input. While the parser returns
           ``None``, call ``on_invalid`` and prompt again.
        3. Record the parsed value with
           ``state.prev_outputs[self.name].add_output(...)``.
        4. Return ``exit_callback(state)``.

        Because ``None`` signals invalid input, a parser cannot use ``None`` as
        a legitimate parsed value.

        Args:
            state: The shared application state.

        Returns:
            The :class:`NodeReturnValue` produced by ``exit_callback``.
        """
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
    """A node that collects exactly one valid input.

    The parsed input is stored as the node's output, then ``exit_callback``
    decides which node runs next. See :class:`Node` for how the flow works.
    """

    def __init__(
        self,
        name: str,
        prompt: Union[Callable[[U], str], str],
        exit_callback: Callable[[U], NodeReturnValue],
        on_invalid: Callable[[str, U], None],
        init_callback: Optional[Callable[[U], None]] = None,
        input_parser: Optional[Callable[[str, U], Optional[T]]] = None,
    ) -> None:
        """Create a single-input node.

        Args:
            name: Unique name of the node.
            prompt: Prompt text, or a callable taking the state and returning
                the prompt text.
            exit_callback: Called with the state after input is recorded;
                returns where to go next.
            on_invalid: Called with the raw input and state when parsing
                fails.
            init_callback: Optional. Called with the state when the node
                starts.
            input_parser: Optional. Parses raw input; return ``None`` to
                reject it. Defaults to using the raw string.
        """
        super().__init__(
            name, prompt, exit_callback, on_invalid, init_callback, input_parser
        )


class LoopingNode(Node):
    """A node that keeps collecting inputs until a quit condition is met.

    Each valid input is parsed and appended to a buffer. After every input,
    ``loop_callback`` (if any) runs, then ``quit_callback`` is checked. When it
    returns ``True`` the loop ends and the whole buffer, a ``list`` of parsed
    values, is stored as the node's output. The input that triggered the quit
    is included in the buffer.

    Attributes:
        quit_callback: Called with the latest parsed input and the state;
            return ``True`` to stop looping.
        loop_callback: Optional. Called after each valid input with the
            parsed input, the buffer so far, and the state.
    """

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
        """Create a looping node.

        Args:
            name: Unique name of the node.
            prompt: Prompt text, or a callable taking the state and returning
                the prompt text. Evaluated before every input.
            quit_callback: Called with the latest parsed input and the state;
                return ``True`` to end the loop.
            exit_callback: Called with the state after the buffer is recorded;
                returns where to go next.
            on_invalid: Called with the raw input and state when parsing
                fails.
            init_callback: Optional. Called with the state once when the node
                starts, before the first prompt.
            input_parser: Optional. Parses raw input; return ``None`` to
                reject it. Defaults to using the raw string.
            loop_callback: Optional. Called after each valid input with the
                parsed input, the buffer of all inputs so far, and the state.
        """
        super().__init__(
            name, prompt, exit_callback, on_invalid, init_callback, input_parser
        )
        self.quit_callback = quit_callback
        self.loop_callback = loop_callback

    def call(self, state: U) -> NodeReturnValue:
        """Run the node: collect inputs until ``quit_callback`` says stop.

        The flow is:

        1. Call ``init_callback(state)`` if provided.
        2. Repeatedly prompt and parse input (re-prompting via ``on_invalid``
           on rejected input), append each valid value to a buffer, and call
           ``loop_callback`` if provided.
        3. Stop once ``quit_callback(parsed_input, state)`` returns ``True``.
        4. Record the buffer with
           ``state.prev_outputs[self.name].add_output(buf)``.
        5. Return ``exit_callback(state)``.

        Args:
            state: The shared application state.

        Returns:
            The :class:`NodeReturnValue` produced by ``exit_callback``.
        """
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
