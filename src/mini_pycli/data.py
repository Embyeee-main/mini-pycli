"""Shared data types for mini-pycli.

This module contains the small building blocks the rest of the library is made
of:

* :class:`BaseState`: the base class every application state must inherit from.
* :class:`NodeOutput`: the per-node history of recorded answers.
* :class:`SpecialReturnValue`: sentinels used for navigation and for rejecting
  input.
* :class:`NodeReturnValue`: what a node hands back to the
  :class:`~mini_pycli.app.App` to say where to go next.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Generic, TypeVar, Union

U = TypeVar("U")


class BaseState:
    """Base class for the shared state passed to every node and callback.

    Subclass this to hold your own application data. :class:`~mini_pycli.app.App`
    refuses to :meth:`~mini_pycli.app.App.init` with a state object that does
    not inherit from it.

    Attributes:
        prev_outputs: Maps node names to their :class:`NodeOutput`. Entries
            are created by :meth:`~mini_pycli.app.App.add_node`.
        running: The app's main loop runs while this is ``True``. Set it to
            ``False`` from any callback to end the program.
        cur_node: Name of the node that is running (or that just finished,
            when read from ``update_callback``). ``None`` before the first
            node starts.

    Note:
        If you subclass with ``@dataclass``, the generated ``__init__`` replaces
        this one, so the attributes above will not exist unless you call
        ``super().__init__()`` yourself, for example from ``__post_init__``::

            @dataclass
            class State(BaseState):
                shop_name: str

                def __post_init__(self) -> None:
                    super().__init__()

        A plain subclass that calls ``super().__init__()`` in its own
        ``__init__`` works too.
    """

    def __init__(self) -> None:
        """Create the bookkeeping attributes used by the app."""
        self.prev_outputs = dict()
        self.running = True
        self.cur_node = None


class NodeOutput(Generic[U]):
    """The history of values a single node has produced.

    Each time a node completes, its result is recorded here. The newest value is
    kept in :attr:`most_recent_output`; the value it replaces is moved to
    :attr:`previous_outputs`. Revisiting a node therefore never loses earlier
    answers.

    For a :class:`~mini_pycli.core_nodes.SingleNode` each value is the parsed
    input. For a :class:`~mini_pycli.core_nodes.LoopingNode` each value is the
    ``list`` of every parsed input from one run of the node (so
    ``previous_outputs`` is a list of lists).

    Attributes:
        most_recent_output: The latest value added, or ``None`` if nothing has
            been added yet.
        previous_outputs: Earlier values, oldest first.
    """

    def __init__(self) -> None:
        """Create an empty output history."""
        self.most_recent_output: U = None
        self.previous_outputs: list[U] = []

    def add_output(self, output: U) -> None:
        """Record a new output.

        The current :attr:`most_recent_output` is appended to
        :attr:`previous_outputs` (unless it is ``None``) and ``output`` becomes
        the new most recent value.

        Because ``None`` means "nothing recorded yet", a node whose parser
        legitimately returns ``None`` will not have that value archived in
        :attr:`previous_outputs` when it is next replaced.

        Args:
            output: The value to record.
        """
        self.previous_outputs.append(self.most_recent_output)
        self.most_recent_output = output


class SpecialReturnValue(Enum):
    """Sentinel values with special meaning to nodes and to the app.

    Attributes:
        LAST_NODE: Return from an ``exit_callback`` (inside a
            :class:`NodeReturnValue`) to move back one step in the app's node
            stack.
        NEXT_NODE: Return from an ``exit_callback`` (inside a
            :class:`NodeReturnValue`) to move forward one step in the app's
            node stack.
        INVALID_INPUT: Return from an ``input_parser`` to reject the input. The
            node calls ``on_invalid`` and prompts again. Any other return
            value, including ``None``, is accepted as the parsed input.
    """

    LAST_NODE = auto()
    NEXT_NODE = auto()
    INVALID_INPUT = auto()


@dataclass
class NodeReturnValue:
    """The result of running a node, telling the app where to go next.

    Attributes:
        next_node: Either the name of the node to run next, or a
            :class:`SpecialReturnValue` (``NEXT_NODE`` / ``LAST_NODE``) to move
            through the node history.
    """

    next_node: Union[str, SpecialReturnValue]
