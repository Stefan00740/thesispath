from datetime import date, timedelta

from app import services

TODAY = date(2026, 1, 15)


def test_readiness_fresh_thesis():
    r = services.compute_readiness(0, 8, False, 0, 5, 0)
    assert r["index"] == 20  # только бонус за дисциплину


def test_readiness_full():
    assert services.compute_readiness(8, 8, True, 5, 5, 0)["index"] == 100


def test_readiness_overdue_penalty():
    assert services.compute_readiness(8, 8, True, 5, 5, 1)["index"] == 90


def test_light_green():
    assert services.traffic_light("in_progress", TODAY + timedelta(days=10), TODAY) == "green"


def test_light_yellow():
    assert services.traffic_light("in_progress", TODAY + timedelta(days=2), TODAY) == "yellow"


def test_light_red_and_accepted_overrides():
    past = TODAY - timedelta(days=1)
    assert services.traffic_light("in_progress", past, TODAY) == "red"
    assert services.traffic_light("accepted", past, TODAY) == "green"


def test_valid_transitions():
    assert services.can_transition("not_started", "in_progress")
    assert services.can_transition("review", "accepted")
    assert services.can_transition("revision", "review")


def test_invalid_transitions():
    assert not services.can_transition("not_started", "accepted")
    assert not services.can_transition("accepted", "review")


def test_forecast_none_without_progress():
    assert services.forecast(0, 8, 30, 60) is None
    assert services.forecast(8, 8, 30, 60) is None


def test_forecast_on_track_and_behind():
    ok = services.forecast(4, 8, 20, 60)   # темп 5 дн/этап, нужно 20, есть 60
    assert ok["on_track"] and ok["delta"] == 40
    bad = services.forecast(1, 8, 50, 60)  # темп 50 дн/этап, нужно 350
    assert not bad["on_track"] and bad["delta"] < 0


def test_badges():
    b = services.badges({"Глава 1"}, 4, 8, 0, False)
    codes = {x["code"] for x in b}
    assert codes == {"first_chapter", "on_time", "halfway"}
    assert services.badges(set(), 1, 8, 1, False) == []
