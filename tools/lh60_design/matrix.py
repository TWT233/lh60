from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from tools.lh60_design.layout import physical_keys


@dataclass(frozen=True)
class MatrixNode:
    logical_index: int
    logical_node_id: str
    physical_key_ids: tuple[str, ...]
    row: int
    column: int
    row_net: str
    column_net: str
    diode_ref: str


@dataclass(frozen=True)
class MatrixGpioMap:
    columns: tuple[str, ...]
    rows: tuple[str, ...]
    spares: tuple[str, ...]


@lru_cache(maxsize=1)
def logical_nodes() -> tuple[MatrixNode, ...]:
    physical_ids_by_node: dict[str, list[str]] = {}
    for key in physical_keys():
        physical_ids_by_node.setdefault(key.logical_node_id, []).append(
            key.physical_key_id
        )

    nodes = []
    for logical_index, (logical_node_id, physical_key_ids) in enumerate(
        physical_ids_by_node.items()
    ):
        row, column = divmod(logical_index, 10)
        nodes.append(
            MatrixNode(
                logical_index=logical_index,
                logical_node_id=logical_node_id,
                physical_key_ids=tuple(physical_key_ids),
                row=row,
                column=column,
                row_net=f"ROW{row}",
                column_net=f"COL{column}",
                diode_ref=f"D{logical_index + 1}",
            )
        )
    return tuple(nodes)


@lru_cache(maxsize=1)
def _nodes_by_physical_key() -> dict[str, MatrixNode]:
    return {
        physical_key_id: node
        for node in logical_nodes()
        for physical_key_id in node.physical_key_ids
    }


def node_for_physical_key(physical_key_id: str) -> MatrixNode:
    return _nodes_by_physical_key()[physical_key_id]


def gpio_map() -> MatrixGpioMap:
    return MatrixGpioMap(
        columns=tuple(f"GP{index}" for index in range(10)),
        rows=("GP10", "GP11", "GP12", "GP13", "GP14", "GP15", "GP26"),
        spares=("GP27", "GP28", "GP29"),
    )
