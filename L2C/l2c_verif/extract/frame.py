from __future__ import annotations


class Frame:
    def __init__(self, page):
        upward = sum(1 for ln in page.lines if ln["dir"] == (0, -1))
        horizontal = sum(1 for ln in page.lines if ln["dir"] == (1, 0))
        self.rot = upward > horizontal
        self.h = page.height
        self.width = page.height if self.rot else page.width

    def box(self, b):
        if not self.rot:
            return tuple(b)
        x0, y0, x1, y1 = b
        return (self.h - y1, x0, self.h - y0, x1)

    def unbox(self, b):
        if not self.rot:
            return list(b)
        x0, y0, x1, y1 = b
        return [y0, self.h - x1, y1, self.h - x0]

    def _direction(self, direction):
        if direction == (0, -1):
            return (1, 0)
        return (0, 1) if direction == (1, 0) else direction

    def lines(self, lines):
        if not self.rot:
            return lines
        return [{**ln, "bbox": self.box(ln["bbox"]), "dir": self._direction(ln["dir"])} for ln in lines]
