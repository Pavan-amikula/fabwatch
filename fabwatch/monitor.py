"""Frozen-reference diagnostics; excursions are investigation clues, not causes."""
import numpy as np


def ewma(values, mean, sigma, lam=.2):
    state = mean; result = []
    t = 0
    for value in values:
        # Missing readings do not invent an observation or advance EWMA time.
        if value is None or not np.isfinite(value):
            continue
        t += 1
        state = lam * value + (1-lam) * state
        width = 3 * sigma * np.sqrt(lam/(2-lam)*(1-(1-lam)**(2*t)))
        result.append({'value': float(state), 'upper': float(mean+width), 'lower': float(mean-width),
                       'excursion': bool(abs(state-mean) > width)})
    return result


def explain(bundle, row):
    median, std = bundle['train_median'], bundle['train_std']
    output = []
    for sensor in bundle['investigation_sensors']:
        i = bundle['columns'].index(sensor); value = row[i]
        if value is None or not np.isfinite(value):
            output.append({'sensor': sensor, 'value': None, 'reference': float(median[i]), 'z': None})
        else:
            output.append({'sensor': sensor, 'value': float(value), 'reference': float(median[i]),
                           'z': float(np.clip((value-median[i])/std[i], -100, 100))})
    return sorted(output, key=lambda r: abs(r['z'] or 0), reverse=True)
