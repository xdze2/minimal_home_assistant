import numpy as np
from scipy.optimize import curve_fit


def exponential_func(t, a, tau, b, t0=0):
    """Target function: y = a * exp(b * x) + c"""
    return a * np.exp(-(t - t0) / tau) + b


def expfit(x, y):
    """Fit exponential function to data and return parameters and R^2 score."""
    # Initial guess for parameters
    a0 = np.max(y) - np.min(y)
    b0 = y[-1]
    tau0 = x[-1] - x[0]
    initial_guess = (a0, tau0, b0)

    t_hat = x - x[0]
    # Fit the curve
    res = curve_fit(
        exponential_func, t_hat, y, p0=initial_guess, maxfev=10000, full_output=False
    )
    popt = res[0]
    print(res)
    # Calculate R^2
    y_pred = exponential_func(t_hat, *popt)
    ss_res = np.std(y - y_pred)
    # ss_tot = np.sum((y - np.mean(y)) ** 2)
    # r2_score = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    return popt, ss_res, y_pred
