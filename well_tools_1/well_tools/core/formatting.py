"""Number/label formatting helpers shared across the app."""

from fractions import Fraction


def decimal_to_pipe_fraction(value, allowed_denominators=(2, 4, 8, 16), max_diff=0.02):
    whole = int(value)
    frac = value - whole
    if abs(frac) < 1e-6:
        return str(whole)
    best_fraction, best_error = None, float("inf")
    for denom in allowed_denominators:
        num = round(frac * denom)
        candidate = num / denom
        error = abs(candidate - frac)
        if error < best_error:
            best_error = error
            best_fraction = Fraction(num, denom)
    if best_error > max_diff:
        return str(value)
    return (f"{whole} {best_fraction.numerator}/{best_fraction.denominator}"
            if best_fraction.numerator != 0 else str(whole))


def format_weight(value):
    s = f'{value:.4f}'.rstrip('0').rstrip('.')
    return s if s else '0'
