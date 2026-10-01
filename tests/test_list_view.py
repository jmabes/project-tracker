import html
import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask
from flask.testing import FlaskClient

from project_tracker import choices
from project_tracker.models import Project
from project_tracker.services import (
    CHOICE_FIELDS,
    SORT_COLUMNS,
    count_projects,
    create_project,
    list_projects,
    parse_list_options,
)

ROW_RE = re.compile(r'<td class="name"><a href="/projects/(\d+)">(.*?)</a></td>')


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


def row_names(text: str) -> list[str]:
    return [html.unescape(name) for _, name in ROW_RE.findall(text)]


def link_href(text: str, label: str) -> str:
    """Return the href of the first link whose text is ``label``."""
    match = re.search(rf'<a href="([^"]*)">\s*{re.escape(label)}\s*</a>', text)
    assert match, f"no link labelled {label!r}"
    return html.unescape(match.group(1))


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.fixture()
def mixed(app: Flask) -> list[Project]:
    """Projects that differ on every column, including finished ones."""
    return [
        make("Alpha", category="Tech", medium="Coding", priority="Low",
             status="In progress", start_date=date(2026, 3, 1),
             estimated_completion_date=date(2026, 12, 1)),
        make("bravo", category="Finance", medium="Research", priority="High",
             status="Not started"),
        make("Charlie", category="Home", medium="Hardware", priority="Medium",
             status="On hold", start_date=date(2025, 1, 1),
             estimated_completion_date=date(2025, 6, 1)),
        make("delta", category="Tech", medium="DIY", priority="High",
             status="Done", start_date=date(2024, 5, 5)),
        make("Echo", category="Home", medium="Coding", priority="Low",
             status="Abandoned", estimated_completion_date=date(2027, 1, 1)),
    ]  # fmt: skip


# --- default view ------------------------------------------------------------


def test_default_view_hides_finished_and_sorts_by_priority(
    client: FlaskClient, mixed: list[Project]
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert row_names(response.text) == ["bravo", "Charlie", "Alpha"]
    assert "Done and Abandoned projects are hidden." in response.text


def test_table_shows_every_column_and_links_names_to_detail(
    client: FlaskClient, mixed: list[Project]
) -> None:
    alpha = mixed[0]

    text = client.get("/").text

    for label in ("Name", "Category", "Medium", "Priority", "Status", "Start date",
                  "Estimated completion"):  # fmt: skip
        assert f">{label}" in text
    row = text[text.index(f'href="/projects/{alpha.id}"') :].split("</tr>")[0]
    for value in ("Alpha", "Tech", "Coding", "Low", "In progress", "2026-03-01",
                  "2026-12-01"):  # fmt: skip
        assert f">{value}<" in row
    # Every listed name links to its own detail page.
    for project_id, name in ROW_RE.findall(text):
        assert client.get(f"/projects/{project_id}").status_code == 200
        assert name in client.get(f"/projects/{project_id}").text


def test_empty_dates_show_a_dash(client: FlaskClient, mixed: list[Project]) -> None:
    text = client.get("/").text
    bravo_row = text[text.index(">bravo<") :].split("</tr>")[0]

    assert bravo_row.count(">—<") == 2


# --- show finished -----------------------------------------------------------


def test_one_click_shows_finished_keeping_filters_and_sort(
    client: FlaskClient, mixed: list[Project]
) -> None:
    page = client.get("/?category=Tech&sort=name&dir=desc")
    assert row_names(page.text) == ["Alpha"]

    href = link_href(page.text, "Show finished projects")
    shown = client.get(href)

    assert query(href) == {
        "category": ["Tech"],
        "show_finished": ["1"],
        "sort": ["name"],
        "dir": ["desc"],
    }
    assert row_names(shown.text) == ["delta", "Alpha"]
    assert count_projects() == len(mixed)  # nothing was deleted


def test_hide_finished_link_turns_it_back_off(
    client: FlaskClient, mixed: list[Project]
) -> None:
    page = client.get("/?show_finished=1&priority=High")
    assert row_names(page.text) == ["bravo", "delta"]

    href = link_href(page.text, "Hide finished projects")

    assert query(href) == {"priority": ["High"]}
    assert row_names(client.get(href).text) == ["bravo"]


@pytest.mark.parametrize("status", choices.FINISHED_STATUSES)
def test_explicit_finished_status_filter_shows_them(
    client: FlaskClient, mixed: list[Project], status: str
) -> None:
    expected = [p.name for p in mixed if p.status == status]

    response = client.get("/", query_string={"status": status})

    assert row_names(response.text) == expected
    assert "Show finished projects</a>" not in response.text


def test_checkbox_reflects_show_finished(
    client: FlaskClient, mixed: list[Project]
) -> None:
    assert 'value="1" checked' not in client.get("/").text
    assert 'value="1" checked' in client.get("/?show_finished=1").text


# --- filters -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field, allowed in CHOICE_FIELDS.items() for value in allowed],
)
def test_each_filter_value(
    client: FlaskClient, mixed: list[Project], field: str, value: str
) -> None:
    args = {field: value, "show_finished": "1"}
    expected = sorted(
        (p for p in mixed if getattr(p, field) == value),
        key=lambda p: (-choices.PRIORITIES[::-1].index(p.priority), p.name.casefold()),
    )

    response = client.get("/", query_string=args)

    assert response.status_code == 200
    assert row_names(response.text) == [p.name for p in expected]
    assert f'<option value="{value}" selected>' in response.text


def test_filters_combine_with_and(client: FlaskClient, mixed: list[Project]) -> None:
    response = client.get("/?category=Home&medium=Coding&show_finished=1")

    assert row_names(response.text) == ["Echo"]


def test_filter_form_is_get_and_keeps_sort(
    client: FlaskClient, mixed: list[Project]
) -> None:
    text = client.get("/?sort=start_date&dir=desc").text

    assert '<form class="filters" method="get" action="/">' in text
    assert '<input type="hidden" name="sort" value="start_date">' in text
    assert '<input type="hidden" name="dir" value="desc">' in text


def test_filter_form_has_no_hidden_sort_on_default_view(
    client: FlaskClient, mixed: list[Project]
) -> None:
    assert 'type="hidden" name="sort"' not in client.get("/").text


def test_filter_options_come_from_choices(client: FlaskClient) -> None:
    text = client.get("/").text

    for allowed in CHOICE_FIELDS.values():
        for value in allowed:
            assert f'<option value="{value}">{value}</option>' in text


# --- sorting -----------------------------------------------------------------


@pytest.mark.parametrize("sort", SORT_COLUMNS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_every_column_sorts_both_ways(
    client: FlaskClient, mixed: list[Project], sort: str, direction: str
) -> None:
    args = {"sort": sort, "dir": direction, "show_finished": "1"}
    expected = [p.name for p in list_projects(parse_list_options(args))]

    response = client.get("/", query_string=args)

    assert response.status_code == 200
    assert row_names(response.text) == expected
    assert len(expected) == len(mixed)


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        ("desc", ["bravo", "delta", "Charlie", "Alpha", "Echo"]),
        ("asc", ["Alpha", "Echo", "Charlie", "bravo", "delta"]),
    ],
)
def test_priority_sorts_by_meaning(
    client: FlaskClient, mixed: list[Project], direction: str, expected: list[str]
) -> None:
    response = client.get(f"/?show_finished=1&sort=priority&dir={direction}")

    assert row_names(response.text) == expected


def test_status_sorts_by_choices_order(
    client: FlaskClient, mixed: list[Project]
) -> None:
    response = client.get("/?show_finished=1&sort=status&dir=asc")

    assert row_names(response.text) == ["bravo", "Alpha", "Charlie", "delta", "Echo"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_empty_start_dates_sort_last(
    client: FlaskClient, mixed: list[Project], direction: str
) -> None:
    response = client.get(f"/?show_finished=1&sort=start_date&dir={direction}")

    assert row_names(response.text)[-2:] == ["bravo", "Echo"]


def test_current_sort_header_flips_direction(
    client: FlaskClient, mixed: list[Project]
) -> None:
    text = client.get("/?sort=name&dir=asc").text

    assert 'aria-sort="ascending"' in text
    assert query(link_href(text, 'Name <span aria-hidden="true">▲</span>')) == {
        "sort": ["name"],
        "dir": ["desc"],
    }


def test_other_headers_use_column_default_direction(
    client: FlaskClient, mixed: list[Project]
) -> None:
    text = client.get("/?category=Tech").text

    # Default sort is priority, High first; clicking it flips to Low first.
    assert 'aria-sort="descending"' in text
    assert query(link_href(text, "Name")) == {
        "category": ["Tech"],
        "sort": ["name"],
        "dir": ["asc"],
    }
    assert query(link_href(text, "Start date")) == {
        "category": ["Tech"],
        "sort": ["start_date"],
        "dir": ["asc"],
    }


# --- invalid query strings ---------------------------------------------------


@pytest.mark.parametrize(
    "query_string",
    [
        "category=Nope",
        "medium=",
        "priority=high",
        "status=Deleted",
        "show_finished=yes",
        "sort=id",
        "sort=name;DROP TABLE projects",
        "dir=sideways",
        "sort=&dir=",
        "category=%FF%FE",
        "priority=High&priority=Low",
        "unknown=1",
        "status=%00",
        "sort=" + "x" * 5000,
    ],
)
def test_invalid_query_values_are_ignored(
    client: FlaskClient, mixed: list[Project], query_string: str
) -> None:
    default = row_names(client.get("/").text)

    response = client.get(f"/?{query_string}")

    assert response.status_code == 200
    if query_string == "priority=High&priority=Low":
        # Only the first value of a repeated key is used.
        assert row_names(response.text) == ["bravo"]
    else:
        assert row_names(response.text) == default


# --- empty states ------------------------------------------------------------


def test_empty_state_when_no_projects_exist(client: FlaskClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "No projects yet." in response.text
    assert 'href="/projects/new"' in response.text
    assert "<table" not in response.text


def test_empty_state_hints_at_hidden_finished_projects(
    client: FlaskClient, mixed: list[Project]
) -> None:
    text = client.get("/?status=On hold&category=Tech").text
    assert "No projects match these filters." in text
    # An explicit status filter already includes finished projects: no hint.
    assert "Show finished projects</a>" not in text

    text = client.get("/?medium=DIY").text

    assert "No projects match these filters." in text
    assert "Done and Abandoned projects are hidden, so some may match." in text
    assert row_names(client.get(link_href(text, "Show finished projects")).text) == [
        "delta"
    ]


def test_empty_state_without_hint_when_finished_shown(
    client: FlaskClient, mixed: list[Project]
) -> None:
    text = client.get("/?medium=DIY&category=Finance&show_finished=1").text

    assert "No projects match these filters." in text
    assert "are hidden" not in text
    assert 'href="/">Clear all filters</a>' in text
