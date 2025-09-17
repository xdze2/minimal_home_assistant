import numpy as np
from typing import List
from dataclasses import dataclass


@dataclass
class Rect:
    left_idx: int
    right_idx: int
    base_height: float
    top_height: float
    parent: "Rect" = None


@dataclass
class RelativeRect:
    left_idx: int
    right_idx: int
    height: float
    base_height: float = None
    parent: "Rect" = None
    removed: bool = False

    def get_base_height(self) -> float:
        if self.base_height is not None:
            return self.base_height
        else:
            return self.parent.get_base_height() + self.parent.height


def horizontal_rectangles_idx(
    Y, left_idx: int = None, right_idx: int = None, base_height: float = 0, parent_rect: Rect = None
) -> List[RelativeRect]:
    """
    Recursive horizontal stacking of rectangles to fill curve area.
    Returns a list of rectangles: (x_start, x_end, y_start, y_end)
    """
    left_idx = 0 if left_idx is None else left_idx
    right_idx = len(Y) - 1 if right_idx is None else right_idx

    if right_idx < left_idx:
        return []

    # Find index of lowest valley in this interval
    min_idx = min(range(left_idx, right_idx + 1), key=lambda i: Y[i])
    min_height = Y[min_idx]

    # Rectangle spans whole interval at the valley height above base
    height = min_height - base_height
    base_height_n = base_height if parent_rect is None else None
    rect = RelativeRect(left_idx, right_idx, height, base_height_n, parent=parent_rect)
    rects = [rect]

    # Recurse left
    if left_idx < min_idx:
        rects += horizontal_rectangles_idx(Y, left_idx, min_idx - 1, min_height, parent_rect=rect)

    # Recurse right
    if min_idx < right_idx:
        rects += horizontal_rectangles_idx(Y, min_idx + 1, right_idx, min_height, parent_rect=rect)

    return rects



def compute_horizontal_rectangles(X: np.array, Y: np.array, base_height: float = 0):
    X = np.asarray(X)
    Y = np.asarray(Y)

    Y_half = (Y[1:] + Y[:-1]) / 2

    rects_idx = horizontal_rectangles_idx(Y_half, base_height=base_height)

    merge_rects(rects_idx, 6)

    rects = list()
    for rect in rects_idx:
        if rect.removed: continue
        x0 = X[rect.left_idx]
        x1 = X[rect.right_idx + 1]
        base_height = rect.get_base_height()
        area = (x1 -x0)*rect.height
        top_height = base_height + rect.height
        rects.append((x0, x1, base_height, top_height, area))

    rects.sort(key=lambda x: x[-1], reverse=True)
    return rects



def merge_rects(rect_list: List[RelativeRect], min_height: float):

    # TODO sort before (greedy)
    for rect in rect_list:
        print("add", rect.height, min_height)
        if rect.height < min_height:
            if rect.parent is None:
                continue
            # add height to parent rect
            parent_width = rect.parent.right_idx - rect.parent.left_idx
            rect.parent.height += rect.height*(rect.right_idx-rect.left_idx)/parent_width
            # TODO merge by area
            rect.removed = True
            for rectB in rect_list:
                if rectB.parent == rect:
                    rectB.parent = rect.parent