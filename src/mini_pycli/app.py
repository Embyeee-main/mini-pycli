"""Application runner for mini-pycli.

:class:`App` owns the shared state, the registered nodes, and the node history
(a stack). Its :meth:`App.mainloop` repeatedly runs the current node and moves
to the next one based on the :class:`~mini_pycli.data.NodeReturnValue` the node
returns, until ``state.running`` becomes ``False``.
"""

from typing import Callable, Optional

from .core_nodes import Node
from .data import BaseState, NodeOutput, SpecialReturnValue


class App:
    """Runs a node-based interactive CLI flow.

    The app holds a user-defined state object that is passed to every node and
    callback. The state must inherit from :class:`~mini_pycli.data.BaseState`,
    which provides three attributes the app relies on:

    * ``running`` (``bool``): the main loop runs while this is ``True``. Set it
      to ``False`` from a callback to end the program.
    * ``prev_outputs`` (``dict[str, NodeOutput]``): the recorded outputs of
      each node, keyed by node name. :meth:`add_node` creates each entry.
    * ``cur_node`` (``str``): the name of the node most recently started by
      the main loop.

    Navigation uses a stack of visited node names. Returning a node name from
    a node pushes that node onto the stack and makes it current;
    ``SpecialReturnValue.LAST_NODE`` and ``SpecialReturnValue.NEXT_NODE`` move
    the current position backward or forward within the stack without changing
    it.

    Typical usage::

        app = App(init_callback=make_state)
        app.init(some_kwarg=...)          # builds the state
        app.add_node(first_node)          # register every node
        app.add_node(second_node)
        app.set_current_node("first")     # choose the starting node
        app.mainloop()                    # run until state.running is False

    Attributes:
        nodes: Registered nodes, keyed by name.
        init_callback: Factory that builds the state object.
        update_callback: Called with the state after every node finishes and
            navigation has been applied, or ``None``.
        exit_callback: Called once with the state after the main loop ends, or
            ``None``.
        state: The state object, or ``None`` before :meth:`init` is called.
        node_stack: Names of visited nodes, in the order they were entered.
        node_stack_index: Index into ``node_stack`` of the current node.
    """

    def __init__(
        self,
        init_callback: Callable[..., BaseState],
        update_callback: Optional[Callable[[BaseState], None]] = None,
        exit_callback: Optional[Callable[[BaseState], None]] = None,
    ) -> None:
        """Create an app.

        Args:
            init_callback: Called by :meth:`init` with its keyword arguments;
                must return an instance of a :class:`~mini_pycli.data.BaseState`
                subclass.
            update_callback: Optional. Called with the state at the end of each
                iteration of the main loop, after navigation has been applied.
                ``state.cur_node`` is still the node that just finished, which
                makes this a convenient place for rendering or bookkeeping.
            exit_callback: Optional. Called once with the state after the main
                loop ends (that is, after ``state.running`` becomes ``False``).
        """
        self.nodes: dict[str, Node] = dict()
        self.init_callback = init_callback
        self.update_callback = update_callback
        self.exit_callback = exit_callback
        self.state: Optional[BaseState] = None
        self.node_stack: list[str] = []
        self.node_stack_index: int = 0

    def init(self, **kwargs) -> None:
        """Build the state object. Must be called before adding nodes.

        Calls ``init_callback(**kwargs)`` and stores the result as
        :attr:`state`.

        Args:
            **kwargs: Passed through to ``init_callback``.

        Raises:
            TypeError: If the returned state does not inherit from
                :class:`~mini_pycli.data.BaseState`.
        """
        self.state = self.init_callback(**kwargs)
        if not isinstance(self.state, BaseState):
            raise TypeError("state must inherit from BaseState")

    def add_node(self, node: Node) -> None:
        """Register a node and create its output history.

        Adds the node to :attr:`nodes` and creates an empty
        :class:`~mini_pycli.data.NodeOutput` for it in
        ``state.prev_outputs[node.name]``.

        Args:
            node: The node to register.

        Raises:
            ValueError: If the app is not initialized, or a node with the same
                name is already registered.
        """
        self._error_if_not_init()
        if self.node_exists(node.name):
            raise ValueError(f"node of name {node.name} already exists")
        self.nodes[node.name] = node
        self.state.prev_outputs[node.name] = NodeOutput()

    def remove_node(self, name: str) -> None:
        """Unregister a node.

        The node's entry in ``state.prev_outputs`` and any occurrences of its
        name in the node stack are left untouched. Running the app while the
        stack still points at a removed node raises ``KeyError``.

        Args:
            name: Name of the node to remove.

        Raises:
            ValueError: If the app is not initialized.
            KeyError: If no node with that name is registered.
        """
        self._error_if_not_init()
        self.nodes.pop(name)

    def get_current_node(self) -> Node:
        """Return the node currently pointed to by the node stack.

        Returns:
            The current :class:`~mini_pycli.core_nodes.Node`.

        Raises:
            ValueError: If the app is not initialized.
            IndexError: If no node has been set yet (empty node stack).
        """
        self._error_if_not_init()
        return self.nodes[self.node_stack[self.node_stack_index]]

    def mainloop(self) -> None:
        """Run the app until ``state.running`` is ``False``.

        Each iteration:

        1. Looks up the current node and sets ``state.cur_node`` to its name.
        2. Runs the node (see :meth:`mini_pycli.core_nodes.Node.call`).
        3. Navigates based on the returned ``next_node``:

           * ``SpecialReturnValue.NEXT_NODE``: move forward in the node stack.
           * ``SpecialReturnValue.LAST_NODE``: move back in the node stack.
           * A string: push that node onto the stack and make it current.

           Moving past either end of the stack does nothing, so the same node
           runs again.
        4. Calls ``update_callback(state)`` if one was given.

        Navigation is applied even on the final iteration, so a node that sets
        ``state.running = False`` must still return a valid ``next_node``
        (``SpecialReturnValue.NEXT_NODE`` is always safe). When the loop ends,
        ``exit_callback(state)`` is called if one was given.

        Use :meth:`set_current_node` to choose the starting node before calling
        this method.

        Raises:
            ValueError: If the app is not initialized, or a node returns a
                name that is not a registered node.
            IndexError: If no starting node has been set.
        """
        self._error_if_not_init()
        while self.state.running:
            cur_node = self.get_current_node()
            self.state.cur_node = cur_node.name
            match (next_node := cur_node.call(self.state).next_node):
                case SpecialReturnValue.NEXT_NODE:
                    self._set_current_node_next_in_stack()
                case SpecialReturnValue.LAST_NODE:
                    self._set_current_node_last_in_stack()
                case _:
                    if not self.set_current_node(next_node):
                        raise ValueError(f"{next_node} is not the name of a node")
            if self.update_callback is not None:
                self.update_callback(self.state)

        if self.exit_callback is not None:
            self.exit_callback(self.state)

    def node_exists(self, name: str) -> bool:
        """Check whether a node is registered.

        Args:
            name: The node name to look up.

        Returns:
            ``True`` if a node with that name is registered.
        """
        return name in self.nodes

    def set_current_node(self, name: str) -> bool:
        """Make a node current by pushing it onto the node stack.

        The name is appended to the end of the stack (history is not
        truncated, even if the index was somewhere in the middle) and the stack
        index is moved to it. Call this once before :meth:`mainloop` to pick the
        starting node.

        Args:
            name: Name of the node to switch to.

        Returns:
            ``True`` on success, ``False`` if no node has that name (in which
            case the stack is unchanged).
        """
        if name not in self.nodes:
            return False
        self.node_stack.append(name)
        self.node_stack_index = len(self.node_stack) - 1
        return True

    def _error_if_not_init(self) -> None:
        """Raise ``ValueError`` if :meth:`init` has not been called."""
        if self.state is None:
            raise ValueError("must initialize app before method is called")

    def _set_current_node_next_in_stack(self) -> bool:
        """Move the stack index forward by one.

        Returns:
            ``True`` if the index moved, ``False`` if already at the end of
            the stack.
        """
        if self.node_stack_index >= len(self.node_stack) - 1:
            return False
        self.node_stack_index += 1
        return True

    def _set_current_node_last_in_stack(self) -> bool:
        """Move the stack index back by one.

        Returns:
            ``True`` if the index moved, ``False`` if already at the start of
            the stack.
        """
        if self.node_stack_index <= 0:
            return False
        self.node_stack_index -= 1
        return True
