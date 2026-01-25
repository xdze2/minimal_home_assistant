import pandas as pd
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import numpy as np
from scipy.optimize import curve_fit


def exponential_func(t, a, tau, b):
    """Target function: y = a * exp(b * x) + c"""
    return a * np.exp(-t / tau) + b


def expfit(x, y):
    """Fit exponential function to data and return parameters and R^2 score."""
    # Initial guess for parameters
    a0 = np.max(y) - np.min(y)
    b0 = y[-1]
    tau0 = 1
    initial_guess = (a0, tau0, b0)

    t_hat = (x - x[0]) / (x[-1] - x[0])
    # Fit the curve
    res = curve_fit(
        exponential_func, t_hat, y, p0=initial_guess, maxfev=10000, full_output=False
    )
    popt = res[0]
    print(res)
    # Calculate R^2
    y_pred = exponential_func(t_hat, *popt)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2_score = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    return popt, r2_score, y_pred


csv_path = "out/sonoff_thermometer_sonoff_thermometer_sensorssthA.csv"

csv_path = Path(csv_path)

df = pd.read_csv(csv_path, parse_dates=["time"])

df["ts"] = df["time"].values.astype(np.int64) // 10**9

time = df["ts"].to_numpy()
temp = df["temperature"].to_numpy()

idx_start = 450
idx_end = 611

x, y = time[idx_start:idx_end], temp[idx_start:idx_end]
popt, r2_score, y_pred = expfit(x, y)

plt.plot(time, temp)
plt.plot(x, y_pred, color="red")


def calculate_iou_1d(seg1, seg2):
    """Calculates Intersection over Union for two 1D segments [start, end]."""
    low = max(seg1[0], seg2[0])
    high = min(seg1[1], seg2[1])
    intersection = max(0, high - low)
    union = (seg1[1] - seg1[0]) + (seg2[1] - seg2[0]) - intersection
    return intersection / union if union > 0 else 0


def detect_exponential_segments(x, y, min_width=10, iou_threshold=0.3, r2_cutoff=0.9):
    candidates = []
    n = len(x)

    # 1. Brute Force Search
    for start in range(0, n - min_width):
        for end in range(start + min_width, n):
            x_seg = x[start:end]
            y_seg = y[start:end]

            try:
                # Initial guesses are important for curve_fit stability

                y_pred = exponential_func(x_seg, *popt)
                # score = r2_score(y_seg, y_pred)

                if score > r2_cutoff:
                    candidates.append(
                        {"range": (start, end), "score": score, "params": popt}
                    )
            except:
                continue

    # 2. Sort by Score (Best fit first)
    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

    # 3. IoU Pruning (Non-Maximum Suppression)
    final_segments = []
    while candidates:
        best = candidates.pop(0)
        final_segments.append(best)

        # Keep only segments that don't overlap too much with the 'best' one
        candidates = [
            c
            for c in candidates
            if calculate_iou_1d(best["range"], c["range"]) < iou_threshold
        ]

    return final_segments


# # --- Example Usage ---
# if __name__ == "__main__":
#     # Generate dummy data with an exponential burst
#     x_data = np.linspace(0, 100, 200)
#     y_data = np.random.normal(0, 0.1, 200) # Noise
#     y_data[50:100] += 0.5 * np.exp(0.08 * np.arange(50)) # Exponential part

#     results = detect_exponential_segments(x_data, y_data)

#     for res in results:
#         print(f"Detected Segment: Indices {res['range']}, R^2: {res['score']:.4f}")


# df = df.sort_values("time")
# fig, ax = plt.subplots(figsize=(12, 5))
# ax.plot(df["time"], df["temperature"], color="#377eb8")

# ax.set_xlabel("Time")
# ax.set_ylabel("Temperature (°C)")
# ax.set_title(f"Temperature: {csv_path.name}")
# ax.grid(alpha=0.3)

# # Format x axis nicely
# ax.xaxis.set_major_locator(mdates.AutoDateLocator())
# ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
# fig.autofmt_xdate()

plt.tight_layout()
out_path = Path("out/sonoff_plot.png")
plt.savefig(out_path, dpi=150)
print(f"Saved plot to {out_path}")
