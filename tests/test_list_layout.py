"""List page markup that the phone layout in style.css relies on."""

import html
import re
from datetime import date

import pytest
from flask import Flask
from flask.testing import FlaskClient

from project_tracker.models import Project
from project_tracker.services import create_project


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


@pytest.fixture()
def projects(app: Flask) -> list[Project]:
    return [
        make(
            "Alpha",
            priority="High",
            status="In progress",
            start_date=date(2026, 3, 1),
            target_date=date(2026, 12, 1),
        ),
        make("Bravo", priority="Low", status="On hold"),
        make("Charlie", status="Done"),
    ]


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i : text.index(end, i)]


def sort_panel(text: str) -> str:
    return between(text, '<details class="sort-panel">', "</details>")


def header_links(text: str) -> list[str]:
    thead = between(text, "<thead>", "</thead>")
    return [html.unescape(h) for h in re.findall(r'<a href="([^"]+)">', thead)]


def chip_links(text: str) -> list[str]:
    nav = between(sort_panel(text), '<nav class="sort-chips"', "</nav>")
    return [html.unescape(h) for h in re.findall(r'<a href="([^"]+)"', nav)]


def summary_text(panel: str) -> str:
    summary = between(panel, "<summary>", "</summary>")
    return " ".join(re.sub(r"<[^>]+>", "", summary).split())


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/", "Sort: Priority ↓, descending"),
        ("/?sort=name&dir=asc", "Sort: Name ↑, ascending"),
        ("/?sort=target_date&dir=desc", "Sort: Target date ↓, descending"),
    ],
)
def test_sort_panel_names_the_current_sort(
    client: FlaskClient, projects: list[Project], url: str, expected: str
) -> None:
    assert summary_text(sort_panel(client.get(url).text)) == expected


def test_sort_chips_use_the_column_heading_links(
    client: FlaskClient, projects: list[Project]
) -> None:
    text = client.get("/?category=Home&sort=status&dir=desc").text
    assert chip_links(text) == header_links(text)
    assert len(chip_links(text)) == 7


def test_only_the_current_sort_chip_is_marked(
    client: FlaskClient, projects: list[Project]
) -> None:
    panel = sort_panel(client.get("/?sort=medium&dir=asc").text)
    current = re.findall(r'<a href="[^"]+" aria-current="true">([^<]+)', panel)
    assert [label.strip() for label in current] == ["Medium"]


def test_no_sort_panel_without_projects(client: FlaskClient, app: Flask) -> None:
    assert '<details class="sort-panel">' not in client.get("/").text


def filter_panel_tag(text: str) -> str:
    return between(text, '<details class="filter-panel"', ">")


def test_filter_panel_is_closed_without_filters(
    client: FlaskClient, projects: list[Project]
) -> None:
    text = client.get("/").text
    assert filter_panel_tag(text) == '<details class="filter-panel"'
    assert 'class="count"' not in text


def test_filter_panel_opens_when_a_choice_filter_is_applied(
    client: FlaskClient, projects: list[Project]
) -> None:
    text = client.get("/?category=Home&priority=Low").text
    assert filter_panel_tag(text) == '<details class="filter-panel" open'
    panel = between(text, '<details class="filter-panel"', "</summary>")
    assert summary_text(panel + "</summary>") == "Filters (2 active)"


def test_show_finished_is_counted_but_keeps_the_panel_closed(
    client: FlaskClient, projects: list[Project]
) -> None:
    text = client.get("/?show_finished=1").text
    assert filter_panel_tag(text) == '<details class="filter-panel"'
    panel = between(text, '<details class="filter-panel"', "</summary>")
    assert summary_text(panel + "</summary>") == "Filters (1 active)"


def test_rows_carry_status_and_priority_for_styling(
    client: FlaskClient, projects: list[Project]
) -> None:
    text = client.get("/?show_finished=1").text
    assert '<td class="priority" data-priority="High">High</td>' in text
    assert (
        '<td class="status"><span class="badge" data-status="On hold">'
        "On hold</span></td>"
    ) in text
    assert '<span class="badge" data-status="Done">Done</span>' in text


def test_empty_dates_are_marked(client: FlaskClient, projects: list[Project]) -> None:
    text = client.get("/").text
    assert '<td class="date start">2026-03-01</td>' in text
    assert '<td class="date target">2026-12-01</td>' in text
    assert '<td class="date start empty">—</td>' in text
    assert '<td class="date target empty">—</td>' in text


@pytest.mark.parametrize(
    ("url", "expected"), [("/", "2 projects"), ("/?status=On+hold", "1 project")]
)
def test_subtitle_counts_the_listed_projects(
    client: FlaskClient, projects: list[Project], url: str, expected: str
) -> None:
    assert f'<p class="subtitle">{expected}</p>' in client.get(url).text
