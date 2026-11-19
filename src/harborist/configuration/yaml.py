"""Shared safe YAML parsing with unambiguous string keys."""

from collections.abc import Hashable

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, ScalarNode


class UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: Node, deep: bool = False
    ) -> dict[Hashable, object]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "Expected a mapping", node.start_mark)
        self.flatten_mapping(node)
        seen: set[str] = set()
        for key_node, _ in node.value:
            if (
                not isinstance(key_node, ScalarNode)
                or key_node.tag != "tag:yaml.org,2002:str"
            ):
                raise ConstructorError(
                    None, None, "Expected a string mapping key", key_node.start_mark
                )
            if key_node.value in seen:
                raise ConstructorError(
                    None, None, "Duplicate mapping key", key_node.start_mark
                )
            seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)
