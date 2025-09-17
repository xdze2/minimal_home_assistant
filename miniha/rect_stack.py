import numpy as np


def horizontal_rectangles_idx(
    Y, left_idx: int = None, right_idx: int = None, base_height: float = 0
) -> list:
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
    rect = (left_idx, right_idx, base_height, min_height)
    rects = [rect]

    # Recurse left
    if left_idx < min_idx:
        rects += horizontal_rectangles_idx(Y, left_idx, min_idx - 1, min_height)

    # Recurse right
    if min_idx < right_idx:
        rects += horizontal_rectangles_idx(Y, min_idx + 1, right_idx, min_height)

    return rects



def compute_horizontal_rectangles(X: np.array, Y: np.array, base_height: float = 0):
    X = np.asarray(X)
    Y = np.asarray(Y)

    Y_half = (Y[1:] + Y[:-1]) / 2

    rects_idx = horizontal_rectangles_idx(Y_half, base_height=base_height)

    rects = list()
    for left_idx, right_idx, base_height, top_height in rects_idx:
        x0 = X[left_idx]
        x1 = X[right_idx + 1]
        area = (x1 - x0) * (top_height - base_height)
        rects.append((x0, x1, base_height, top_height, area))

    rects.sort(key=lambda x: x[-1], reverse=True)
    return rects
