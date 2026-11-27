"""Core node types for mini-pycli.

A mini-pycli program is a graph of *nodes*. Each node prompts the user for
input, parses and validates it, records the result on the shared application
state, and then tells the :class:`~mini_pycli.app.App` which node to run next.

Two concrete node types are provided:

* :class:`SingleNode` collects one valid input.
* :class:`LoopingNode` keeps collecting inputs until a quit condition is met.

Nodes are driven by an :class:`~mini_pycli.app.App`, which supplies the shared
``state`` object passed to every callback. The state must inherit from
:class:`~mini_pycli.data.BaseState`; the app registers a
:class:`~mini_pycli.data.NodeOutput` for each node in ``state.prev_outputs``.

Callback signatures at a glance (``state`` is always your state object)::

    prompt          str | (state) -> str
    input_parser    (raw_text, state) -> parsed value | SpecialReturnValue.INVALID_INPUT
    on_invalid      (raw_text, state) -> None
    init_callback   (state) -> None
    exit_callback   (state) -> NodeReturnValue
    quit_callback   (parsed_value, state) -> bool                  [LoopingNode]
    loop_callback   (parsed_value, buffer, state) -> None          [LoopingNode]
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from .data import NodeReturnValue, SpecialReturnValue, U


@dataclass
class Node:
    """Base class for a prompt-driven step in a CLI flow.

    A node prompts the user, parses the input, stores the result in the shared
    state, and returns a :class:`~mini_pycli.data.NodeReturnValue`. Prefer the
    concrete :class:`SingleNode` and :class:`LoopingNode` subclasses.

    Attributes:
        name: Unique name of the node. Used to register it with the app, to
            jump to it from other nodes, and as the key into
            ``state.prev_outputs``.
        prompt: Text shown to the user, or a callable that takes the state and
            returns the text (useful for dynamic prompts). A callable is
            re-evaluated before every prompt.
        exit_callback: Called with the state after the node's input has been
            recorded. Returns a :class:`~mini_pycli.data.NodeReturnValue`
            choosing the next node.
        on_invalid: Called with the raw input and the state whenever
            ``input_parser`` rejects the input. Typically used to print an
            error message.
        init_callback: Optional. Called with the state once each time the node
            starts, before the first prompt.
        input_parser: Optional. Called with the raw input string and the state.
            Returns the parsed value, or
            :attr:`SpecialReturnValue.INVALID_INPUT <mini_pycli.data.SpecialReturnValue.INVALID_INPUT>`
            to reject the input. Any other return value (including ``None``)
            is accepted. If omitted, the raw string is used as-is.
    """

    name: str
    prompt: Union[Callable[[U], str], str]
    exit_callback: Callable[[U], NodeReturnValue]
    on_invalid: Callable[[str, U], None]
    init_callback: Optional[Callable[[U], None]] = None
    input_parser: Optional[Callable[[str, U], Any]] = None

    def call(self, state: U) -> NodeReturnValue:
        """Run the node: prompt until valid input is given, then exit.

        The flow is:

        1. Call ``init_callback(state)`` if provided.
        2. Prompt the user (with the built-in ``input``) and parse the input.
           While the parser returns ``SpecialReturnValue.INVALID_INPUT``, call
           ``on_invalid(raw_input, state)`` and prompt again.
        3. Record the parsed value with
           ``state.prev_outputs[self.name].add_output(...)``.
        4. Return ``exit_callback(state)``.

        Args:
            state: The shared application state.

        Returns:
            The :class:`~mini_pycli.data.NodeReturnValue` produced by
            ``exit_callback``.
        """
        if self.init_callback is not None:
            self.init_callback(state)

        while True:
            cur_input = input(
                self.prompt(state) if isinstance(self.prompt, Callable) else self.prompt
            )

            parsed_input = (
                self.input_parser(cur_input, state)
                if self.input_parser is not None
                else cur_input
            )

            if parsed_input is not SpecialReturnValue.INVALID_INPUT:
                break

            self.on_invalid(cur_input, state)

        state.prev_outputs[self.name].add_output(parsed_input)
        return self.exit_callback(state)


class SingleNode(Node):
    """A node that collects exactly one valid input.

    The parsed input is stored as the node's output, then ``exit_callback``
    decides which node runs next. See :class:`Node` for the full flow.

    Example:
        >>> ask_age = SingleNode(
        ...     name="age",
        ...     prompt="Age? ",
        ...     input_parser=lambda text, state: (
        ...         int(text) if text.isdigit() else SpecialReturnValue.INVALID_INPUT
        ...     ),
        ...     on_invalid=lambda text, state: print("Digits only, please."),
        ...     exit_callback=lambda state: NodeReturnValue("next_step"),
        ... )
    """

    def __init__(
        self,
        name: str,
        prompt: Union[Callable[[U], str], str],
        exit_callback: Callable[[U], NodeReturnValue],
        on_invalid: Callable[[str, U], None],
        init_callback: Optional[Callable[[U], None]] = None,
        input_parser: Optional[Callable[[str, U], Any]] = None,
    ) -> None:
        """Create a single-input node.

        Args:
            name: Unique name of the node.
            prompt: Prompt text, or a callable taking the state and returning
                the prompt text.
            exit_callback: Called with the state after the input is recorded;
                returns where to go next.
            on_invalid: Called with the raw input and the state when parsing
                fails.
            init_callback: Optional. Called with the state when the node
                starts.
            input_parser: Optional. Parses raw input; return
                ``SpecialReturnValue.INVALID_INPUT`` to reject it. Defaults to
                using the raw string.
        """
        super().__init__(
            name, prompt, exit_callback, on_invalid, init_callback, input_parser
        )


class LoopingNode(Node):
    """A node that keeps collecting inputs until a quit condition is met.

    Each valid input is parsed and appended to a buffer. After every valid
    input, ``loop_callback`` (if any) runs, then ``quit_callback`` is checked.
    When it returns ``True`` the loop ends and the whole buffer, a ``list`` of
    parsed values, is stored as the node's output. The input that triggered the
    quit is included in the buffer. Rejected inputs are never added to the
    buffer and never reach ``quit_callback``.

    Attributes:
        quit_callback: Called with the latest parsed input and the state;
            return ``True`` to stop looping.
        loop_callback: Optional. Called after each valid input with the parsed
            input, the buffer so far, and the state.
    """

    def __init__(
        self,
        name: str,
        prompt: Union[Callable[[U], str], str],
        quit_callback: Callable[[Any, U], bool],
        exit_callback: Callable[[U], NodeReturnValue],
        on_invalid: Callable[[str, U], None],
        init_callback: Optional[Callable[[U], None]] = None,
        input_parser: Optional[Callable[[str, U], Any]] = None,
        loop_callback: Optional[Callable[[Any, list, U], None]] = None,
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
            on_invalid: Called with the raw input and the state when parsing
                fails.
            init_callback: Optional. Called with the state once when the node
                starts, before the first prompt.
            input_parser: Optional. Parses raw input; return
                ``SpecialReturnValue.INVALID_INPUT`` to reject it. Defaults to
                using the raw string.
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
           ``loop_callback(parsed_input, buffer, state)`` if provided.
        3. Stop once ``quit_callback(parsed_input, state)`` returns ``True``.
        4. Record the buffer with
           ``state.prev_outputs[self.name].add_output(buffer)``.
        5. Return ``exit_callback(state)``.

        Args:
            state: The shared application state.

        Returns:
            The :class:`~mini_pycli.data.NodeReturnValue` produced by
            ``exit_callback``.
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

                if parsed_input is not SpecialReturnValue.INVALID_INPUT:
                    break

                self.on_invalid(cur_input, state)

            buf.append(parsed_input)
            if self.loop_callback is not None:
                self.loop_callback(parsed_input, buf, state)

            if self.quit_callback(parsed_input, state):
                break

        state.prev_outputs[self.name].add_output(buf)
        return self.exit_callback(state)
