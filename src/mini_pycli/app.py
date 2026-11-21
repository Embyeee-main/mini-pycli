from typing import Any, Callable, Optional, TypeVar

from .core_nodes import Node, NodeOutput, SpecialReturnValue

T = TypeVar("T")


class App:
    def __init__(self, init_callback: Callable[Any, T]) -> None:
        self.nodes: dict[str, Node] = dict()
        self.init_callback = init_callback
        self.state: Optional[T] = None
        self.node_stack: list[str] = []
        self.node_stack_index: int = 0

    def init(self, **kwargs) -> None:
        self.state = self.init_callback(**kwargs)
        self.state.__dict__["running"] = True
        self.state.__dict__["prev_outputs"] = dict()

    def add_node(self, node: Node) -> None:
        self._error_if_not_init()
        if self.node_exists(node.name):
            raise ValueError(f"node of name {node.name} already exists")
        self.nodes[node.name] = node
        self.state.prev_outputs[node.name] = NodeOutput()

    def remove_node(self, name: str) -> None:
        self._error_if_not_init()
        self.nodes.pop(name)

    def get_current_node(self) -> Node:
        self._error_if_not_init()
        return self.node_stack[self.node_stack_index]

    def mainloop(self) -> None:
        self._error_if_not_init()
        while self.state.running:
            cur_node = self.get_current_node()
            match (next_node := cur_node.call(self.state).next_node):
                case SpecialReturnValue.NEXT_NODE:
                    self._set_current_node_next_in_stack()
                case SpecialReturnValue.LAST_NODE:
                    self._set_current_node_last_in_stack()
                case _:
                    if not self.set_current_node(next_node):
                        raise ValueError(
                            f"{next_node} is not the name of a node")

    def node_exists(self, name: str) -> bool:
        return name in self.nodes

    def set_current_node(self, name: str) -> Optional[bool]:
        if name not in self.nodes:
            return False
        self.node_stack.append(name)
        self.node_stack_index = len(self.node_stack) - 1

    def _error_if_not_init(self) -> None:
        if self.state is None:
            raise ValueError("must initialize app before mainloop is called")

    def _set_current_node_next_in_stack(self) -> Optional[bool]:
        if self.node_stack_index >= len(self.node_stack):
            return False
        self.node_stack_index += 1

    def _set_current_node_last_in_stack(self) -> Optional[bool]:
        if self.node_stack_index < 0:
            return False
        self.node_stack_index -= 1
