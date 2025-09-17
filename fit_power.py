import numpy as np
import matplotlib.pyplot as plt
from rich.pretty import pprint

import pandas as pd
import matplotlib.patches as patches


from miniha.rect_stack import compute_horizontal_rectangles




def generate_random_data():
    n_points = 200
    steps = np.random.randn(n_points)
    Y = np.cumsum(steps)
    Y = np.array(Y - np.min(Y) + 1)
    X = np.sort(np.cumsum(1 + 0.5 * np.random.randn(n_points)))
    X = X - np.min(X)
    return X, Y

input_file = "images/power_2025-09-09.csv"
print(f"load dataframe from {input_file}")
df = pd.read_csv(input_file)


df = df[:150]
df["date"] = pd.to_datetime(df["date"])
X_hours = (df["date"] - df["date"][0]).dt.total_seconds() / (60 * 60)
Y = df["power"]


rects = compute_horizontal_rectangles(X_hours, Y)
print(f"First {len(rects)} Rectangles (x_start, x_end, y_start, y_end):")
for r in rects[:5]:
    print(r)

print("Plot curve with rectangles...")
fig, ax = plt.subplots(figsize=(12, 6))

ax.plot(X_hours, Y, marker=".", label="samples", alpha=0.7)
# ax.plot(X_half, Y_half, linestyle="None", marker="x", label="middle points", alpha=0.7)


for x0, x1, y0, y1, area in rects:
    width = x1 - x0
    height = y1 - y0
    rect_patch = patches.Rectangle(
        (x0, y0), width, height, facecolor="orange", alpha=0.3, edgecolor="red"
    )
    ax.add_patch(rect_patch)

ax.set_title("Horizontal Rectangle Decomposition")
ax.set_xlabel("X")
ax.set_ylabel("Y")
# ax.set_yscale("log")
ax.legend()
output_file = "fit502.png"
plt.savefig(output_file)
print(f"figure saved to {output_file}")
