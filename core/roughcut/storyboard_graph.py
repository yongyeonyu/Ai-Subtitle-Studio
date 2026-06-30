from __future__ import annotations

from dataclasses import dataclass


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
    "clamp_storyboard_row",
    "initial_storyboard_grid_slots",
    "sorted_storyboard_nodes_by_grid",
    "source_color_for_storyboard_node",
    "storyboard_role_for_outgoing_index",
    "storyboard_role_for_row",
    "storyboard_row_duration_seconds",
    "storyboard_row_for_role",
]
