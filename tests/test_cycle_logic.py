from datetime import date, timedelta
from types import SimpleNamespace

from cycle_logic import DEFAULT_CYCLE_DAYS, DEFAULT_PERIOD_DAYS, calc_stats, get_phase


def cycle(start, end=None):
    return SimpleNamespace(start_date=start, end_date=end)


def test_no_cycles_falls_back_to_defaults():
    stats = calc_stats([])
    assert stats["avg_cycle"] == DEFAULT_CYCLE_DAYS
    assert stats["avg_period"] == DEFAULT_PERIOD_DAYS
    assert stats["irregular"] is False
    assert stats["next_period"] is None
    assert stats["total"] == 0


def test_regular_cycles_average_and_prediction():
    start = date(2026, 1, 1)
    cycles = [cycle(start + timedelta(days=28 * i), start + timedelta(days=28 * i + 4)) for i in range(4)]
    stats = calc_stats(cycles)
    assert stats["avg_cycle"] == 28
    assert stats["avg_period"] == 5  # 5-day periods (inclusive of start day)
    assert stats["irregular"] is False
    assert stats["next_period"] == str(start + timedelta(days=28 * 3 + 28))


def test_irregular_cycles_are_detected():
    start = date(2026, 1, 1)
    # gaps of 21 and 40 days: spread of 19 days, above the 7-day threshold
    cycles = [cycle(start), cycle(start + timedelta(days=21)), cycle(start + timedelta(days=61))]
    assert calc_stats(cycles)["irregular"] is True


def test_implausible_gaps_are_ignored():
    start = date(2026, 1, 1)
    # a 5-day gap is a duplicate log, not a real cycle; it must not drag the average down
    cycles = [cycle(start), cycle(start + timedelta(days=5)), cycle(start + timedelta(days=33))]
    stats = calc_stats(cycles)
    assert stats["avg_cycle"] == 28  # only the 28-day gap is kept
    assert stats["irregular"] is False


def test_single_cycle_still_predicts_next_period():
    start = date(2026, 3, 1)
    stats = calc_stats([cycle(start, start + timedelta(days=4))])
    assert stats["next_period"] == str(start + timedelta(days=DEFAULT_CYCLE_DAYS))


def test_cycles_are_sorted_before_use():
    start = date(2026, 1, 1)
    cycles = [cycle(start + timedelta(days=28)), cycle(start)]  # out of order
    assert calc_stats(cycles)["avg_cycle"] == 28


def test_phase_boundaries():
    start = date(2026, 1, 1)
    expected = {1: "menstrual", 5: "menstrual", 6: "follicular", 13: "follicular",
                14: "ovulation", 16: "ovulation", 17: "luteal", 28: "luteal", 29: "late"}
    for day, phase in expected.items():
        today = start + timedelta(days=day - 1)
        assert get_phase(start, 28, today=today) == phase, f"day {day}"


def test_phase_unknown_without_data_or_future_start():
    assert get_phase(None, 28) == "unknown"
    assert get_phase(date(2030, 1, 1), 28, today=date(2026, 1, 1)) == "unknown"
