"""Cycle-tracking rules: averages, irregularity and the current phase.

Pure Python with no Flask or database imports, so every rule can be unit-tested
with plain objects. Any object with ``start_date`` and ``end_date`` attributes works.
"""
from datetime import date, timedelta

DEFAULT_CYCLE_DAYS = 28
DEFAULT_PERIOD_DAYS = 5

# Gaps and period lengths outside these ranges are usually missed logs, so they are ignored.
VALID_CYCLE_GAP_DAYS = (15, 50)
VALID_PERIOD_LENGTH_DAYS = (1, 10)

# A spread of more than this many days between cycle gaps counts as "irregular".
IRREGULAR_SPREAD_DAYS = 7

PHASE_INFO = {
    "menstrual":  {"label": "Menstrual Phase",  "color": "#D4537E", "tip": "Rest and stay warm. Iron-rich foods recommended."},
    "follicular": {"label": "Follicular Phase", "color": "#378ADD", "tip": "Energy is rising — good time for new activities."},
    "ovulation":  {"label": "Ovulation Phase",  "color": "#1D9E75", "tip": "Peak energy day. Great time for exercise."},
    "luteal":     {"label": "Luteal Phase",     "color": "#BA7517", "tip": "You may feel bloated. Magnesium-rich foods help."},
    "late":       {"label": "Late Cycle",       "color": "#7F77DD", "tip": "Period may be approaching soon."},
    "unknown":    {"label": "Log Your Cycle",   "color": "#888",    "tip": "Add your period dates to see cycle insights."},
}


def calc_stats(cycles):
    """Summarise a user's logged cycles.

    Returns the average cycle length, average period length, whether the cycle is
    irregular, the predicted next period start, and the number of cycles.
    """
    sorted_cycles = sorted(cycles, key=lambda c: c.start_date)

    gaps = [
        (later.start_date - earlier.start_date).days
        for earlier, later in zip(sorted_cycles, sorted_cycles[1:])
    ]
    gaps = [g for g in gaps if VALID_CYCLE_GAP_DAYS[0] <= g <= VALID_CYCLE_GAP_DAYS[1]]

    lengths = [
        (c.end_date - c.start_date).days + 1
        for c in sorted_cycles if c.end_date
    ]
    lengths = [n for n in lengths if VALID_PERIOD_LENGTH_DAYS[0] <= n <= VALID_PERIOD_LENGTH_DAYS[1]]

    avg_cycle = round(sum(gaps) / len(gaps)) if gaps else DEFAULT_CYCLE_DAYS
    avg_period = round(sum(lengths) / len(lengths)) if lengths else DEFAULT_PERIOD_DAYS
    irregular = bool(gaps) and (max(gaps) - min(gaps) > IRREGULAR_SPREAD_DAYS)

    next_period = None
    if sorted_cycles:
        next_period = sorted_cycles[-1].start_date + timedelta(days=avg_cycle)

    return {
        "avg_cycle": avg_cycle,
        "avg_period": avg_period,
        "irregular": irregular,
        "next_period": next_period.isoformat() if next_period else None,
        "total": len(sorted_cycles),
    }


def get_phase(last_start, avg_cycle, today=None):
    """Return the phase name for ``today`` given the start of the latest cycle.

    Day 1 is the first day of the period. The phase boundaries are fixed day ranges
    (a simple, explainable rule set, not a hormone model).
    """
    if not last_start:
        return "unknown"
    today = today or date.today()
    day = (today - last_start).days + 1
    if day < 1:
        return "unknown"  # start date is in the future
    if day <= 5:
        return "menstrual"
    if day <= 13:
        return "follicular"
    if day <= 16:
        return "ovulation"
    if day <= avg_cycle:
        return "luteal"
    return "late"
