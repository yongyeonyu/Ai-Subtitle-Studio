from core.roughcut.storyboard_graph import (
    STORYBOARD_ROW_COUNT,
    build_storyboard_layout_plan,
    selected_storyboard_connection_sequence,
    storyboard_parallel_group_grid_slots,
)


def test_selected_storyboard_connection_sequence_uses_main_lane_and_keeps_unlinked_nodes():
    nodes = [1, 2, 3, 4, 5]
    connections = {
        1: [2, 3],
        2: [4],
    }
    roles = {
        (1, 2): "sub1",
        (1, 3): "main",
        (2, 4): "main",
    }

    assert selected_storyboard_connection_sequence(nodes, connections, roles, {}) == [1, 3, 2, 4, 5]


def test_storyboard_layout_plan_builds_grid_vectors_without_dropping_cards():
    nodes = list(range(1, 9))
    connections = {
        1: [2, 3, 4, 5, 6, 7, 8],
    }
    roles = {
        (1, 2): "main",
        (1, 3): "sub1",
        (1, 4): "sub2",
        (1, 5): "sub3",
        (1, 6): "sub4",
        (1, 7): "sub5",
        (1, 8): "sub5",
    }

    plan = build_storyboard_layout_plan(nodes, connections, roles)

    assert sorted(plan.order) == nodes
    assert len(plan.order) == len(nodes)
    assert len(plan.vectors) == 7
    assert plan.grid_slots[1] == (0, 0)
    assert plan.grid_slots[2] == (0, 1)
    assert plan.grid_slots[3] == (1, 1)
    assert plan.grid_slots[4] == (2, 1)
    assert plan.grid_slots[7] == (5, 1)
    assert plan.grid_slots[8] == (5, 2)
    assert all(0 <= row < STORYBOARD_ROW_COUNT for row, _col in plan.grid_slots.values())
    assert plan.vectors[0].source == 1
    assert plan.vectors[0].target == 2
    assert plan.vectors[0].delta_col == 1
    assert plan.vectors[0].manhattan_grid_distance == 1
    assert plan.vectors[-1].role == "sub5"
    assert plan.vectors[-1].delta_col == 2


def test_storyboard_layout_plan_preserves_cycles_as_stable_vectors():
    nodes = [1, 2, 3, 4]
    connections = {
        1: [2],
        2: [3],
        3: [1],
    }
    roles = {
        (1, 2): "main",
        (2, 3): "main",
        (3, 1): "main",
    }

    plan = build_storyboard_layout_plan(nodes, connections, roles)

    assert sorted(plan.order) == nodes
    assert len(plan.vectors) == 3
    assert {vector.source for vector in plan.vectors} == {1, 2, 3}


def test_storyboard_layout_plan_anchors_lane_root_without_dropping_cards():
    nodes = list(range(1, 9))

    plan = build_storyboard_layout_plan(nodes, {}, {}, lane_anchors={2: 7})

    assert sorted(plan.order) == nodes
    assert len(plan.order) == len(nodes)
    assert plan.grid_slots[7] == (2, 0)
    assert plan.grid_slots[3] == (2, 1)
    assert plan.vectors[0].source == -3
    assert plan.vectors[0].target == 7
    assert plan.vectors[0].role == "sub2"


def test_storyboard_layout_plan_anchors_lane_root_parallel_targets():
    nodes = list(range(1, 9))

    plan = build_storyboard_layout_plan(
        nodes,
        {},
        {},
        lane_anchor_targets={2: [7, 8, 6]},
        lane_anchor_target_roles={(2, 7): "main", (2, 8): "sub1", (2, 6): "sub2"},
    )

    assert sorted(plan.order) == nodes
    assert plan.grid_slots[7] == (2, 0)
    assert plan.grid_slots[8] == (1, 0)
    assert plan.grid_slots[6] == (3, 0)
    assert [(vector.source, vector.target, vector.role) for vector in plan.vectors[:3]] == [
        (-3, 7, "main"),
        (-3, 8, "sub1"),
        (-3, 6, "sub2"),
    ]
    assert [vector.target_row for vector in plan.vectors[:3]] == [2, 1, 3]


def test_storyboard_layout_plan_keeps_random_ten_card_goal_from_lane_root():
    target_order = [5, 1, 3, 9, 10, 7, 2, 6, 4, 8]
    connections = {
        source: [target]
        for source, target in zip(target_order, target_order[1:])
    }
    roles = {
        (source, target): "main"
        for source, target in zip(target_order, target_order[1:])
    }

    plan = build_storyboard_layout_plan(
        list(range(1, 11)),
        connections,
        roles,
        lane_anchors={0: target_order[0]},
    )

    assert plan.order == tuple(target_order)
    assert [plan.grid_slots[node] for node in target_order] == [
        (0, index)
        for index in range(len(target_order))
    ]
    assert [vector.target for vector in plan.vectors[: len(target_order)]] == target_order


def test_storyboard_parallel_group_grid_slots_supports_three_one_three_three_layout():
    nodes = list(range(1, 11))

    slots = storyboard_parallel_group_grid_slots(nodes, (3, 1, 3, 3))

    assert [slots[node] for node in nodes] == [
        (0, 0),
        (1, 0),
        (2, 0),
        (0, 1),
        (0, 2),
        (1, 2),
        (2, 2),
        (0, 3),
        (1, 3),
        (2, 3),
    ]


def test_storyboard_layout_plan_can_apply_three_one_three_three_parallel_columns():
    nodes = list(range(1, 11))

    plan = build_storyboard_layout_plan(
        nodes,
        {},
        {},
        parallel_column_counts=(3, 1, 3, 3),
    )

    assert plan.order == tuple(nodes)
    assert [plan.grid_slots[node] for node in nodes] == [
        (0, 0),
        (1, 0),
        (2, 0),
        (0, 1),
        (0, 2),
        (1, 2),
        (2, 2),
        (0, 3),
        (1, 3),
        (2, 3),
    ]
