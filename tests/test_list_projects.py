from datetime import date

import pytest
from flask import Flask

from project_tracker import choices
from project_tracker.models import Project
from project_tracker.services import (
    CHOICE_FIELDS,
    DEFAULT_SORT,
    SORT_COLUMNS,
    ListOptions,
    count_projects,
    create_project,
    list_projects,
    parse_list_options,
)


def make(name: str, **overrides: object) -> Project:
    raw: dict[str, object] = {
        "name": name,
        "category": "Home",
        "medium": "DIY",
        "priority": "Medium",
        "status": "Not started",
    }
    raw.update(overrides)
    return create_project(raw)


def names(options: ListOptions) -> list[str]:
    return [project.name for project in list_projects(options)]


# --- parse_list_options ----------------------------------------------------


def test_no_query_string_gives_defaults() -> None:
    options = parse_list_options({})

    assert options == ListOptions()
    assert options.category is None
    assert options.medium is None
    assert options.priority is None
    assert options.status is None
    assert options.show_finished is False
    assert options.hides_finished is True
    assert (options.sort, options.direction) == ("priority", "desc")


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field, allowed in CHOICE_FIELDS.items() for value in allowed],
)
def test_parses_every_allowed_filter_value(field: str, value: str) -> None:
    options = parse_list_options({field: value})

    assert getattr(options, field) == value


@pytest.mark.parametrize("field", list(CHOICE_FIELDS))
@pytest.mark.parametrize("value", ["", "nope", "high", " High", "Done; DROP TABLE"])
def test_ignores_invalid_filter_values(field: str, value: str) -> None:
    assert getattr(parse_list_options({field: value}), field) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("0", False), ("", False), ("yes", False), ("true", False)],
)
def test_parses_show_finished(value: str, expected: bool) -> None:
    assert parse_list_options({"show_finished": value}).show_finished is expected


@pytest.mark.parametrize("sort", SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_parses_every_sort_column_and_direction(sort: str, direction: str) -> None:
    options = parse_list_options({"sort": sort, "dir": direction})

    assert (options.sort, options.direction) == (sort, direction)


@pytest.mark.parametrize("sort", ["", "id", "created_at", "NAME", "name desc"])
def test_ignores_invalid_sort_column(sort: str) -> None:
    assert parse_list_options({"sort": sort}).sort == DEFAULT_SORT


@pytest.mark.parametrize(
    ("sort", "expected"),
    [("priority", "desc"), ("name", "asc"), ("start_date", "asc")],
)
@pytest.mark.parametrize("direction", [None, "", "up", "DESC"])
def test_missing_or_invalid_direction_uses_column_default(
    sort: str, expected: str, direction: str | None
) -> None:
    args = {"sort": sort} if direction is None else {"sort": sort, "dir": direction}

    assert parse_list_options(args).direction == expected


@pytest.mark.parametrize(
    ("sort", "expected"),
    [("priority", "desc"), ("name", "asc"), ("status", "asc")],
)
def test_options_without_direction_use_column_default(sort: str, expected: str) -> None:
    # Regression: sort="name" used to inherit priority's "desc".
    assert ListOptions(sort=sort).direction == expected


def test_explicit_status_filter_stops_hiding_finished() -> None:
    assert parse_list_options({"status": "Done"}).hides_finished is False
    assert parse_list_options({"show_finished": "1"}).hides_finished is False


def test_default_options_have_no_query_args() -> None:
    assert ListOptions().query_args() == {}


@pytest.mark.parametrize(
    "options",
    [
        ListOptions(category="Tech", medium="Coding", priority="High"),
        ListOptions(status="On hold", sort="name", direction="desc"),
        ListOptions(show_finished=True, sort="start_date", direction="asc"),
        ListOptions(sort="priority", direction="asc"),
    ],
)
def test_query_args_round_trip(options: ListOptions) -> None:
    assert parse_list_options(options.query_args()) == options


# --- list_projects: filters --------------------------------------------------


def test_default_list_hides_done_and_abandoned(app: Flask) -> None:
    for status in choices.STATUSES:
        make(status, status=status)

    assert sorted(names(ListOptions())) == ["In progress", "Not started", "On hold"]
    # Hidden, never deleted.
    assert count_projects() == len(choices.STATUSES)


def test_show_finished_lists_every_status(app: Flask) -> None:
    for status in choices.STATUSES:
        make(status, status=status)

    assert sorted(names(ListOptions(show_finished=True))) == sorted(choices.STATUSES)


@pytest.mark.parametrize("status", choices.FINISHED_STATUSES)
def test_explicit_finished_status_filter_shows_those_projects(
    app: Flask, status: str
) -> None:
    for each in choices.STATUSES:
        make(each, status=each)

    assert names(ListOptions(status=status)) == [status]


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field, allowed in CHOICE_FIELDS.items() for value in allowed],
)
def test_each_filter_keeps_only_matching_projects(
    app: Flask, field: str, value: str
) -> None:
    # One project per allowed value of this field, all with a visible status
    # unless the field is status itself.
    for each in CHOICE_FIELDS[field]:
        make(f"p-{each}", **{field: each})

    assert names(ListOptions(show_finished=True, **{field: value})) == [f"p-{value}"]


def test_filters_combine_with_and(app: Flask) -> None:
    make("match", category="Tech", medium="Coding", priority="High")
    make("wrong category", category="Home", medium="Coding", priority="High")
    make("wrong medium", category="Tech", medium="DIY", priority="High")
    make("wrong priority", category="Tech", medium="Coding", priority="Low")
    make("finished match", category="Tech", medium="Coding", priority="High",
         status="Done")  # fmt: skip

    options = ListOptions(category="Tech", medium="Coding", priority="High")

    assert names(options) == ["match"]
    assert names(options.replace(show_finished=True)) == ["finished match", "match"]


def test_empty_database_lists_nothing(app: Flask) -> None:
    assert list_projects(ListOptions()) == []
    assert count_projects() == 0


# --- list_projects: sorting --------------------------------------------------


def test_default_sort_is_priority_high_first_then_name(app: Flask) -> None:
    make("b low", priority="Low")
    make("a high", priority="High")
    make("c medium", priority="Medium")
    make("b high", priority="High")

    assert names(ListOptions()) == ["a high", "b high", "c medium", "b low"]


def test_priority_desc_means_high_first(app: Flask) -> None:
    for priority in ("Low", "High", "Medium"):
        make(priority, priority=priority)

    assert names(ListOptions(sort="priority", direction="desc")) == [
        "High",
        "Medium",
        "Low",
    ]
    assert names(ListOptions(sort="priority", direction="asc")) == [
        "Low",
        "Medium",
        "High",
    ]


def test_status_sorts_by_order_in_choices(app: Flask) -> None:
    for status in sorted(choices.STATUSES):  # insert alphabetically
        make(status, status=status)

    options = ListOptions(show_finished=True, sort="status")

    assert names(options.replace(direction="asc")) == list(choices.STATUSES)
    assert names(options.replace(direction="desc")) == list(reversed(choices.STATUSES))


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("category", ["Finance", "Home", "Tech"]),
        ("medium", ["Coding", "DIY", "Hardware", "Research"]),
    ],
)
def test_category_and_medium_sort_alphabetically(
    app: Flask, field: str, values: list[str]
) -> None:
    for value in reversed(values):
        make(value, **{field: value})

    options = ListOptions(sort=field)

    assert names(options.replace(direction="asc")) == values
    assert names(options.replace(direction="desc")) == list(reversed(values))


def test_name_sorts_ignoring_case(app: Flask) -> None:
    for name in ("banana", "Apple", "cherry", "APRICOT"):
        make(name)

    options = ListOptions(sort="name")

    assert names(options.replace(direction="asc")) == [
        "Apple",
        "APRICOT",
        "banana",
        "cherry",
    ]
    assert names(options.replace(direction="desc")) == [
        "cherry",
        "banana",
        "APRICOT",
        "Apple",
    ]


def test_name_sort_folds_non_ascii_case_like_uniqueness(app: Flask) -> None:
    # SQLite's lower() leaves "É" alone, which would put "ÉZ" before "éa".
    make("ÉZ project")
    make("éa project")

    assert names(ListOptions(sort="name")) == ["éa project", "ÉZ project"]


@pytest.mark.parametrize("field", ["start_date", "target_date"])
def test_dates_sort_with_empty_dates_last_both_ways(app: Flask, field: str) -> None:
    make("empty one")
    make("late", start_date=date(2026, 1, 1), target_date=date(2026, 9, 1))
    make("empty two")
    make("early", start_date=date(2025, 1, 1), target_date=date(2025, 9, 1))

    options = ListOptions(sort=field)

    assert names(options.replace(direction="asc")) == [
        "early",
        "late",
        "empty one",
        "empty two",
    ]
    assert names(options.replace(direction="desc")) == [
        "late",
        "early",
        "empty one",
        "empty two",
    ]


@pytest.mark.parametrize("sort", SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_ties_break_by_name(app: Flask, sort: str, direction: str) -> None:
    # Identical except for name, so every column ties except name itself.
    for name in ("charlie", "Alpha", "bravo"):
        make(name)

    result = names(ListOptions(sort=sort, direction=direction))

    if sort == "name" and direction == "desc":
        assert result == ["charlie", "bravo", "Alpha"]
    else:
        assert result == ["Alpha", "bravo", "charlie"]
