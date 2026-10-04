from __future__ import annotations

SAME_LINE_TOL = 0.3
SAME_LINE_REACH = 3.0
PAIR_RADIUS = 0.6
NEAR_SAME_VALUE_RADIUS = 0.8


def _dist(p: dict, s: dict) -> float:
    return ((p["u"][0] - s["u"][0]) ** 2 + (p["u"][1] - s["u"][1]) ** 2) ** 0.5


def _offsets(p: dict, s: dict) -> tuple[float, float]:
    dx, dy = abs(p["u"][0] - s["u"][0]), abs(p["u"][1] - s["u"][1])
    return (dx, dy) if p["axis"] == "V" else (dy, dx)


def _same_value(p: dict, s: dict) -> bool:
    sizes_differ = p["size"] and s["size"] and p["size"] != s["size"]
    return p["n"] in s["n_alts"] and p["m"] == s["m"] and not sizes_differ


def _both_differ(p: dict, s: dict) -> bool:
    return p["n"] not in s["n_alts"] and p["m"] != s["m"]


def _doubts(p: dict, s: dict, d: float, shop: list[dict], j: int) -> list[str]:
    why = list(dict.fromkeys(p.get("amb", []) + s.get("amb", [])))
    reach = max(1.25 * d, d + 0.1)
    if any(k != j and o["axis"] == p["axis"] and _dist(p, o) <= reach for k, o in enumerate(shop)):
        why.append("competing shop annotation nearby")
    return why


def _mark_weak(p: dict, s: dict, why: list[str]) -> None:
    if why:
        for annotation in (p, s):
            annotation["weak"] = list(dict.fromkeys(annotation.get("weak", []) + why))


def _adopt_plan_reading(p: dict, s: dict) -> dict:
    if p["n"] != s["n"] and p["n"] in s["n_alts"]:
        return {**s, "n": p["n"], "text": s["text"] + f" (reading {p['n']}({p['m']}))"}
    return s


class _Pairing:
    def __init__(self, plan: list[dict], shop: list[dict]):
        self.plan, self.shop = plan, shop
        self.used_plan: set[int] = set()
        self.used_shop: set[int] = set()
        self.pairs: list[tuple] = []

    def _free(self, i: int, j: int) -> bool:
        return i not in self.used_plan and j not in self.used_shop

    def _take(self, i: int, j: int) -> None:
        self.used_plan.add(i)
        self.used_shop.add(j)

    def _accept_near(self, d: float, i: int, j: int, exact: bool) -> None:
        self._take(i, j)
        p, s = self.plan[i], _adopt_plan_reading(self.plan[i], self.shop[j])
        if not exact:
            why = _doubts(p, s, d, self.shop, j)
            if _both_differ(p, s):
                why.append("both numbers differ")
            _mark_weak(p, s, why)
        self.pairs.append((p, s))

    def _near_candidates(self) -> list[tuple]:
        return [
            (_dist(p, s), i, j)
            for i, p in enumerate(self.plan)
            for j, s in enumerate(self.shop)
            if p["axis"] == s["axis"] and _dist(p, s) <= PAIR_RADIUS
        ]

    def _near_order(self, candidates: list[tuple], exact: bool) -> list[tuple]:
        if exact:
            return sorted(candidates)
        return sorted(candidates, key=lambda c: (_both_differ(self.plan[c[1]], self.shop[c[2]]), c[0]))

    def _eligible(self, i: int, j: int, exact: bool) -> bool:
        p, s = self.plan[i], self.shop[j]
        if not self._free(i, j) or exact != _same_value(p, s):
            return False
        return exact or p["loc"] == s["loc"]

    def nearby(self) -> None:
        candidates = self._near_candidates()
        for exact in (True, False):
            for d, i, j in self._near_order(candidates, exact):
                if self._eligible(i, j, exact):
                    self._accept_near(d, i, j, exact)

    def _same_cell_candidates(self) -> list[tuple]:
        return [
            (_dist(self.plan[i], self.shop[j]), i, j)
            for i in range(len(self.plan))
            for j in range(len(self.shop))
            if self._free(i, j)
            and self.plan[i]["axis"] == self.shop[j]["axis"]
            and self.plan[i]["loc"] == self.shop[j]["loc"]
            and not _both_differ(self.plan[i], self.shop[j])
        ]

    def same_cell(self) -> None:
        candidates = self._same_cell_candidates()
        for d, i, j in sorted(
            candidates, key=lambda c: (not _same_value(self.plan[c[1]], self.shop[c[2]]), c[0])
        ):
            if not self._free(i, j):
                continue
            self._take(i, j)
            p, s = self.plan[i], _adopt_plan_reading(self.plan[i], self.shop[j])
            if not _same_value(p, s):
                why = _doubts(p, s, d, self.shop, j)
                if d > PAIR_RADIUS:
                    why.append("texts far apart")
                _mark_weak(p, s, why)
            self.pairs.append((p, s))

    def _mutual_match(self, i: int, free_plan: list[int], free_shop: list[int]) -> int | None:
        p = self.plan[i]
        candidates = [j for j in free_shop if self.shop[j]["axis"] == p["axis"]]
        if not candidates:
            return None
        j = min(candidates, key=lambda k: _dist(p, self.shop[k]))
        rivals = [k for k in free_plan if k not in self.used_plan and self.plan[k]["axis"] == p["axis"]]
        mutual = min(rivals, key=lambda k: _dist(self.plan[k], self.shop[j])) == i
        close = _same_value(p, self.shop[j]) and _dist(p, self.shop[j]) <= NEAR_SAME_VALUE_RADIUS
        return j if mutual and close else None

    def mutual_nearest(self) -> None:
        free_plan = [i for i in range(len(self.plan)) if i not in self.used_plan]
        free_shop = [j for j in range(len(self.shop)) if j not in self.used_shop]
        for i in free_plan:
            j = self._mutual_match(i, free_plan, free_shop)
            if j is not None:
                self._take(i, j)
                free_shop.remove(j)
                self.pairs.append((self.plan[i], self.shop[j]))

    def same_line(self) -> None:
        aligned = []
        for i, p in enumerate(self.plan):
            for j, s in enumerate(self.shop):
                if not self._free(i, j) or p["axis"] != s["axis"] or not _same_value(p, s):
                    continue
                across, along = _offsets(p, s)
                if across <= SAME_LINE_TOL and along <= SAME_LINE_REACH:
                    aligned.append((across, along, i, j))
        for _, _, i, j in sorted(aligned):
            if self._free(i, j):
                self._take(i, j)
                self.pairs.append((self.plan[i], self.shop[j]))

    def result(self) -> list[tuple]:
        unmatched_plan = [(p, None) for i, p in enumerate(self.plan) if i not in self.used_plan]
        unmatched_shop = [(None, s) for j, s in enumerate(self.shop) if j not in self.used_shop]
        return self.pairs + unmatched_plan + unmatched_shop


def pair_annotations(plan: list[dict], shop: list[dict]) -> list[tuple]:
    pairing = _Pairing(plan, shop)
    pairing.nearby()
    pairing.same_cell()
    pairing.mutual_nearest()
    pairing.same_line()
    return pairing.result()
