from __future__ import annotations

from collections.abc import Iterable


def union_bbox(boxes: Iterable) -> list[float]:
    boxes = list(boxes)
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def lines_bbox(lines: Iterable[dict]) -> list[float]:
    return union_bbox(ln["bbox"] for ln in lines)


def center(bbox) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def connected_groups(count: int, links: Iterable[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(count))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in links:
        parent[root(j)] = root(i)
    groups: dict[int, list[int]] = {}
    for i in range(count):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())
