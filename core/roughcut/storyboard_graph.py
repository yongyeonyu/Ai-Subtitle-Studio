from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


STORYBOARD_ROW_LABELS = ("메인", "예비1", "예비2", "예비3", "예비4", "예비5")
STORYBOARD_MAIN_ROW = 0
STORYBOARD_ROW_COUNT = len(STORYBOARD_ROW_LABELS)
STORYBOARD_ROW_ROLE_NAMES = ("main", "sub1", "sub2", "sub3", "sub4", "sub5")
STORYBOARD_ROW_ROLE_BY_ROW = dict(enumerate(STORYBOARD_ROW_ROLE_NAMES))
STORYBOARD_ROW_BY_ROLE = {role: row for row, role in STORYBOARD_ROW_ROLE_BY_ROW.items()}

STORYBOARD_CONNECTION_ROLE_COLORS = {
    "main": "#34C759",
    "sub1": "#0A84FF",
    "sub2": "#FF2D93",
    "sub3": "#FF9F0A",
    "sub4": "#AF52DE",
    "sub5": "#FFD60A",
}

STORYBOARD_SOURCE_COLORS = (
    "#34C759",
    "#0A84FF",
    "#FF2D93",
    "#FF9F0A",
    "#AF52DE",
    "#64D2FF",
    "#FFD60A",
    "#30D158",
    "#BF5AF2",
    "#FF453A",
    "#5E5CE6",
    "#AC8E68",
)


@dataclass(frozen=True)
class StoryboardInsert:
    row: int
    col: int

    @property
    def linear_slot(self) -> int:
        return (self.col * STORYBOARD_ROW_COUNT) + self.row


@dataclass(frozen=True)
class StoryboardSortVector:
    ordinal: int
    source: int
    target: int
    role: str
    source_row: int
    source_col: int
    target_row: int
    target_col: int
    delta_row: int
    delta_col: int
    manhattan_grid_distance: int


@dataclass(frozen=True)
class StoryboardLayoutPlan:
    order: tuple[int, ...]
    grid_slots: dict[int, tuple[int, int]]
    vectors: tuple[StoryboardSortVector, ...]


def clamp_storyboard_row(row: int) -> int:
    return max(0, min(STORYBOARD_ROW_COUNT - 1, int(row)))


def storyboard_role_for_row(row: int) -> str:
    return STORYBOARD_ROW_ROLE_BY_ROW.get(clamp_storyboard_row(row), "main")


def storyboard_row_for_role(role: str) -> int:
    return STORYBOARD_ROW_BY_ROLE.get(str(role or "main"), STORYBOARD_MAIN_ROW)


def storyboard_role_for_outgoing_index(index: int) -> str:
    index = max(0, int(index))
    if index >= len(STORYBOARD_ROW_ROLE_NAMES):
        index = len(STORYBOARD_ROW_ROLE_NAMES) - 1
    return STORYBOARD_ROW_ROLE_NAMES[index]


def storyboard_parallel_anchor_rows(source_row: int) -> tuple[int, ...]:
    source_row = clamp_storyboard_row(source_row)
    rows = [source_row]
    for distance in range(1, STORYBOARD_ROW_COUNT):
        for candidate in (source_row - distance, source_row + distance):
            if 0 <= candidate < STORYBOARD_ROW_COUNT and candidate not in rows:
                rows.append(candidate)
    return tuple(rows)


def initial_storyboard_grid_slots(nodes: list[int]) -> dict[int, tuple[int, int]]:
    return {
        node: (index % STORYBOARD_ROW_COUNT, index // STORYBOARD_ROW_COUNT)
        for index, node in enumerate(nodes)
    }


def source_color_for_storyboard_node(source_node: int) -> str:
    source_node = max(1, int(source_node or 1))
    return STORYBOARD_SOURCE_COLORS[(source_node - 1) % len(STORYBOARD_SOURCE_COLORS)]


def sorted_storyboard_nodes_by_grid(
    nodes: list[int],
    grid_slots: dict[int, tuple[int, int]],
) -> list[int]:
    return sorted(
        nodes,
        key=lambda node: (
            grid_slots.get(node, (STORYBOARD_MAIN_ROW, 0))[1],
            grid_slots.get(node, (STORYBOARD_MAIN_ROW, 0))[0],
            node,
        ),
    )


def storyboard_parallel_group_grid_slots(
    nodes: Sequence[int],
    group_counts: Sequence[int],
    *,
    start_row: int = STORYBOARD_MAIN_ROW,
) -> dict[int, tuple[int, int]]:
    active_nodes = [int(node) for node in nodes]
    row_start = clamp_storyboard_row(start_row)
    row_capacity = max(1, STORYBOARD_ROW_COUNT - row_start)
    slots: dict[int, tuple[int, int]] = {}
    node_index = 0
    col = 0
    for raw_count in group_counts:
        count = max(0, min(row_capacity, int(raw_count)))
        if count <= 0:
            continue
        for row_offset in range(count):
            if node_index >= len(active_nodes):
                break
            slots[active_nodes[node_index]] = (row_start + row_offset, col)
            node_index += 1
        col += 1
        if node_index >= len(active_nodes):
            break
    while node_index < len(active_nodes):
        for row_offset in range(row_capacity):
            if node_index >= len(active_nodes):
                break
            slots[active_nodes[node_index]] = (row_start + row_offset, col)
            node_index += 1
        col += 1
    return slots


def selected_storyboard_connection_sequence(
    nodes: Sequence[int],
    connections: Mapping[int, Sequence[int]],
    connection_roles: Mapping[tuple[int, int], str] | None = None,
    parallel_selections: Mapping[int, int] | None = None,
) -> list[int]:
    active_order = [int(node) for node in nodes]
    active_set = set(active_order)
    roles = connection_roles or {}
    selections = parallel_selections or {}
    selected_edges: dict[int, int] = {}
    incoming: set[int] = set()
    for source, targets in connections.items():
        source = int(source)
        if source not in active_set:
            continue
        valid_targets = [int(target) for target in targets if int(target) in active_set]
        if not valid_targets:
            continue
        main_targets = [
            target
            for target in valid_targets
            if roles.get((source, target), storyboard_role_for_outgoing_index(valid_targets.index(target))) == "main"
        ]
        selected = int(selections.get(source, 0) or 0)
        target = main_targets[0] if main_targets else selected
        if target not in valid_targets:
            target = valid_targets[0]
        selected_edges[source] = target
        incoming.add(target)

    roots = [node for node in active_order if node not in incoming]
    sequence: list[int] = []
    seen: set[int] = set()
    for start in roots or active_order:
        current = start
        while current and current in active_set and current not in seen:
            sequence.append(current)
            seen.add(current)
            current = selected_edges.get(current, 0)
    for node in active_order:
        if node not in seen:
            sequence.append(node)
    return sequence


def _shift_storyboard_row_right(
    slots: dict[int, tuple[int, int]],
    *,
    row: int,
    col: int,
    ignored_node: int,
) -> None:
    for occupant, slot in sorted(list(slots.items()), key=lambda item: item[1][1], reverse=True):
        if occupant == ignored_node:
            continue
        slot_row, slot_col = slot
        if slot_row == row and slot_col >= col:
            slots[occupant] = (slot_row, slot_col + 1)


def build_storyboard_layout_plan(
    nodes: Sequence[int],
    connections: Mapping[int, Sequence[int]],
    connection_roles: Mapping[tuple[int, int], str] | None = None,
    *,
    parallel_selections: Mapping[int, int] | None = None,
    lane_anchors: Mapping[int, int] | None = None,
    lane_anchor_roles: Mapping[int, str] | None = None,
    lane_anchor_targets: Mapping[int, Sequence[int]] | None = None,
    lane_anchor_target_roles: Mapping[tuple[int, int], str] | None = None,
    parallel_column_counts: Sequence[int] | None = None,
    parallel_column_start_row: int = STORYBOARD_MAIN_ROW,
    deleted_nodes: Iterable[int] = (),
) -> StoryboardLayoutPlan:
    deleted = {int(node) for node in deleted_nodes}
    active_nodes = [int(node) for node in nodes if int(node) not in deleted]
    roles = dict(connection_roles or {})
    sequence = selected_storyboard_connection_sequence(
        active_nodes,
        connections,
        roles,
        parallel_selections,
    )
    active_set = set(sequence)
    anchor_roles = {
        clamp_storyboard_row(row): str(role or "main")
        for row, role in (lane_anchor_roles or {}).items()
    }
    anchor_target_roles = {
        (clamp_storyboard_row(row), int(target)): str(role or "main")
        for (row, target), role in (lane_anchor_target_roles or {}).items()
    }
    anchor_targets: dict[int, tuple[int, ...]] = {}
    if lane_anchor_targets is not None:
        for raw_row, raw_targets in lane_anchor_targets.items():
            row = clamp_storyboard_row(raw_row)
            targets: list[int] = []
            for raw_target in raw_targets:
                target = int(raw_target)
                if target in active_set and target not in targets:
                    targets.append(target)
            if targets:
                anchor_targets[row] = tuple(targets)
    else:
        for raw_row, raw_target in (lane_anchors or {}).items():
            row = clamp_storyboard_row(raw_row)
            target = int(raw_target)
            if target in active_set:
                anchor_targets[row] = (target,)

    anchor_items: list[tuple[int, int, int, str]] = []
    for row, targets in sorted(anchor_targets.items()):
        for branch_index, target in enumerate(targets):
            role = anchor_target_roles.get((row, target))
            if role is None:
                role = (
                    anchor_roles.get(row, storyboard_role_for_row(row))
                    if branch_index == 0
                    else storyboard_role_for_outgoing_index(branch_index)
                )
            anchor_items.append((row, target, branch_index, role))

    if parallel_column_counts:
        slots = storyboard_parallel_group_grid_slots(
            sequence,
            parallel_column_counts,
            start_row=parallel_column_start_row,
        )
    else:
        slots = initial_storyboard_grid_slots(sequence)

        for row, target, branch_index, _role in anchor_items:
            anchor_rows = storyboard_parallel_anchor_rows(row)
            target_row = anchor_rows[min(branch_index, len(anchor_rows) - 1)]
            _shift_storyboard_row_right(slots, row=target_row, col=0, ignored_node=target)
            slots[target] = (target_row, 0)

        placed_targets_by_source_row: dict[tuple[int, int], set[int]] = {}
        for source in sequence:
            source = int(source)
            if source not in active_set:
                continue
            source_row, source_col = slots.get(source, (STORYBOARD_MAIN_ROW, 0))
            for target in connections.get(source, ()):
                target = int(target)
                if target not in active_set:
                    continue
                role = roles.get((source, target), storyboard_role_for_outgoing_index(0))
                target_row = storyboard_row_for_role(role)
                target_col = source_col + 1
                placed_same_lane = placed_targets_by_source_row.setdefault((source, target_row), set())
                while any(
                    occupant != target and occupant in placed_same_lane and slot == (target_row, target_col)
                    for occupant, slot in slots.items()
                ):
                    target_col += 1
                _shift_storyboard_row_right(slots, row=target_row, col=target_col, ignored_node=target)
                slots[target] = (target_row, target_col)
                placed_same_lane.add(target)

    order = tuple(sorted_storyboard_nodes_by_grid(sequence, slots))
    vectors: list[StoryboardSortVector] = []
    ordinal = 0
    for row, target, _branch_index, role in anchor_items:
        target_row, target_col = slots[target]
        vectors.append(
            StoryboardSortVector(
                ordinal=ordinal,
                source=-(row + 1),
                target=target,
                role=role,
                source_row=row,
                source_col=-1,
                target_row=target_row,
                target_col=target_col,
                delta_row=target_row - row,
                delta_col=target_col + 1,
                manhattan_grid_distance=abs(target_row - row) + abs(target_col + 1),
            )
        )
        ordinal += 1
    for source in order:
        source_targets = [int(target) for target in connections.get(source, ()) if int(target) in active_set]
        for target in source_targets:
            role = roles.get((source, target), storyboard_role_for_outgoing_index(source_targets.index(target)))
            source_row, source_col = slots[source]
            target_row, target_col = slots[target]
            delta_row = target_row - source_row
            delta_col = target_col - source_col
            vectors.append(
                StoryboardSortVector(
                    ordinal=ordinal,
                    source=source,
                    target=target,
                    role=role,
                    source_row=source_row,
                    source_col=source_col,
                    target_row=target_row,
                    target_col=target_col,
                    delta_row=delta_row,
                    delta_col=delta_col,
                    manhattan_grid_distance=abs(delta_row) + abs(delta_col),
                )
            )
            ordinal += 1
    return StoryboardLayoutPlan(order=order, grid_slots=dict(slots), vectors=tuple(vectors))


def storyboard_row_duration_seconds(
    nodes: list[int],
    trim_state: dict[int, dict[str, int]],
    *,
    base_duration: float = 10.0,
) -> float:
    total = 0.0
    for node in nodes:
        trim = trim_state.get(node, {})
        left = float(trim.get("left", 0) or 0)
        right = float(trim.get("right", 0) or 0)
        total += max(0.1, float(base_duration) + right - left)
    return round(total, 3)


__all__ = [
    "STORYBOARD_CONNECTION_ROLE_COLORS",
    "STORYBOARD_MAIN_ROW",
    "STORYBOARD_ROW_BY_ROLE",
    "STORYBOARD_ROW_COUNT",
    "STORYBOARD_ROW_LABELS",
    "STORYBOARD_ROW_ROLE_BY_ROW",
    "STORYBOARD_ROW_ROLE_NAMES",
    "STORYBOARD_SOURCE_COLORS",
    "StoryboardInsert",
    "StoryboardLayoutPlan",
    "StoryboardSortVector",
    "build_storyboard_layout_plan",
    "clamp_storyboard_row",
    "initial_storyboard_grid_slots",
    "sorted_storyboard_nodes_by_grid",
    "source_color_for_storyboard_node",
    "selected_storyboard_connection_sequence",
    "storyboard_parallel_anchor_rows",
    "storyboard_parallel_group_grid_slots",
    "storyboard_role_for_outgoing_index",
    "storyboard_role_for_row",
    "storyboard_row_duration_seconds",
    "storyboard_row_for_role",
]
