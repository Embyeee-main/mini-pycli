"""Application runner for mini-pycli.

:class:`App` owns the shared state, the registered nodes, and the node history
(a stack). Its :meth:`App.mainloop` repeatedly runs the current node and moves
to the next one based on the node's :class:`~mini_pycli.core_nodes.NodeReturnValue`
until ``state.running`` becomes ``False``.
"""

from typing import Callable, Optional, TypeVar

from .core_nodes import Node, NodeOutput, SpecialReturnValue

T = TypeVar("T")


class App:
    """Runs a node-based interactive CLI flow.

    The app holds a user-defined state object that is passed to every node and
    callback. On :meth:`init`, two attributes are injected into the state:

    * ``running`` (``bool``): the main loop runs while this is ``True``. Set it
      to ``False`` from a callback to end the program.
    * ``prev_outputs`` (``dict[str, NodeOutput]``): the recorded outputs of
      each node, keyed by node name.
    * ``cur_node`` (``str``): The name of the current node

    The state object must therefore support attribute assignment through
    ``__dict__`` (e.g. a regular class or non-slotted dataclass).

    Navigation uses a stack of visited node names. Jumping to a node by name
    pushes it onto the stack; :class:`~mini_pycli.core_nodes.SpecialReturnValue`
    values move the current position backward or forward within that stack.

    Attributes:
        nodes: Registered nodes, keyed by name.
        init_callback: Factory that builds the state object.
        update_callback: Called with the state after every node finishes.
        state: The state object, or ``None`` before :meth:`init` is called.
        node_stack: Names of visited nodes, in the order they were entered.
        node_stack_index: Index into ``node_stack`` of the current node.
    """

    def __init__(self, init_callback: Callable[..., T], update_callback: Callable[T, None]) -> None:
        """Create an app.

        Args:
            init_callback: Called by :meth:`init` with its keyword arguments;
                must return the state object.
            update_callback: Called with the state at the end of each
                iteration of the main loop, after navigation has been
                applied. Useful for rendering or bookkeeping.
        """
        self.nodes: dict[str, Node] = dict()
        self.init_callback = init_callback
        self.update_callback = update_callback
        self.state: Optional[T] = None
        self.node_stack: list[str] = []
        self.node_stack_index: int = 0

    def init(self, **kwargs) -> None:
        """Build the state and prepare it for use.

        Calls ``init_callback(**kwargs)`` to create the state, then adds the
        ``running`` flag (``True``) and an empty ``prev_outputs`` mapping to
        it. This must be called before adding nodes or running the app.

        Args:
            **kwargs: Passed through to ``init_callback``.
        """
        self.state = self.init_callback(**kwargs)
        self.state.__dict__["running"] = True
        self.state.__dict__["prev_outputs"] = dict()
        self.state.__dict__["cur_node"] = None

    def add_node(self, node: Node) -> None:
        """Register a node and create its output history.

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

        The node's entry in ``state.prev_outputs`` and any occurrences in the
        node stack are left untouched.

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

        Each iteration runs the current node, then navigates based on the
        returned ``next_node``:

        * ``SpecialReturnValue.NEXT_NODE``: move forward in the node stack.
        * ``SpecialReturnValue.LAST_NODE``: move back in the node stack.
        * A string: push that node onto the stack and make it current.

        After navigation, ``update_callback`` is called with the state. Use
        :meth:`set_current_node` to choose the starting node before calling
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
                        raise ValueError(
                            f"{next_node} is not the name of a node")
            self.update_callback(self.state)

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
        truncated) and the stack index is moved to it.

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
