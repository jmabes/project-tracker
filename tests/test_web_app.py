import json
import re
import struct
from pathlib import Path
from urllib.parse import urljoin

import pytest
from flask.testing import FlaskClient

from scripts import make_icon

STATIC = Path(__file__).resolve().parent.parent / "project_tracker" / "static"
MANIFEST_URL = "/static/manifest.webmanifest"
ICON_URL = "/static/apple-touch-icon.png"


def head_of(client: FlaskClient, url: str) -> str:
    response = client.get(url)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    return text[: text.index("</head>")]


@pytest.mark.parametrize("url", ["/", "/projects/new", "/import/"])
def test_every_page_links_the_manifest_and_icon(client: FlaskClient, url: str) -> None:
    head = head_of(client, url)
    assert f'<link rel="manifest" href="{MANIFEST_URL}">' in head
    assert f'<link rel="apple-touch-icon" href="{ICON_URL}">' in head
    assert '<meta name="apple-mobile-web-app-title" content="Projects">' in head
    assert re.search(r'<meta name="theme-color" content="#[0-9a-f]{6}"', head)


def test_manifest_is_served_as_manifest_json(client: FlaskClient) -> None:
    with client.get(MANIFEST_URL) as response:
        assert response.status_code == 200
        assert response.mimetype == "application/manifest+json"
        manifest = json.loads(response.get_data(as_text=True))
    assert manifest["name"] == "Project Tracker"
    assert manifest["short_name"] == "Projects"
    # Standalone is the display mode iOS supports for home-screen web apps.
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["id"] == "/"


def test_manifest_theme_color_matches_the_meta_tag(client: FlaskClient) -> None:
    with client.get(MANIFEST_URL) as response:
        manifest = json.loads(response.get_data(as_text=True))
    head = head_of(client, "/")
    assert f'<meta name="theme-color" content="{manifest["theme_color"]}"' in head


def test_manifest_icons_resolve_to_served_pngs(client: FlaskClient) -> None:
    with client.get(MANIFEST_URL) as response:
        manifest = json.loads(response.get_data(as_text=True))
    assert manifest["icons"]
    for icon in manifest["icons"]:
        # Icon URLs are relative to the manifest's own URL.
        url = urljoin(MANIFEST_URL, icon["src"])
        with client.get(url) as response:
            assert response.status_code == 200
            assert response.mimetype == icon["type"] == "image/png"


def png_header(data: bytes) -> tuple[int, int, int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    length, kind = struct.unpack(">I4s", data[8:16])
    assert (length, kind) == (13, b"IHDR")
    width, height, depth, colour_type = struct.unpack(">IIBB", data[16:26])
    return width, height, depth, colour_type


def test_icon_is_served_as_a_180px_opaque_png(client: FlaskClient) -> None:
    with client.get(ICON_URL) as response:
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        data = response.get_data()
    # 180x180, 8-bit truecolour without alpha: iOS masks the corners itself.
    assert png_header(data) == (180, 180, 8, 2)


def test_committed_icon_matches_the_generator_script() -> None:
    assert (STATIC / "apple-touch-icon.png").read_bytes() == make_icon.render_png()
