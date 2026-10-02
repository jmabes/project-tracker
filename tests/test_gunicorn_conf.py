import runpy
from pathlib import Path
from typing import Any

import pytest

CONF = Path(__file__).resolve().parent.parent / "gunicorn.conf.py"


def _load(monkeypatch: pytest.MonkeyPatch, **env: str) -> dict[str, Any]:
    for name in ("PROJECT_TRACKER_HOST", "PROJECT_TRACKER_PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(CONF))


def test_bind_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    conf = _load(
        monkeypatch, PROJECT_TRACKER_HOST="0.0.0.0", PROJECT_TRACKER_PORT="8002"
    )

    assert conf["bind"] == ["0.0.0.0:8002"]


def test_bind_defaults_to_localhost_8002(monkeypatch: pytest.MonkeyPatch) -> None:
    conf = _load(monkeypatch)

    assert conf["bind"] == ["127.0.0.1:8002"]


def test_blank_values_use_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    conf = _load(monkeypatch, PROJECT_TRACKER_HOST=" ", PROJECT_TRACKER_PORT="")

    assert conf["bind"] == ["127.0.0.1:8002"]


@pytest.mark.parametrize("port", ["eighty", "0", "65536", "-1", "80.5"])
def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    with pytest.raises(ValueError, match="PROJECT_TRACKER_PORT"):
        _load(monkeypatch, PROJECT_TRACKER_PORT=port)


def test_serves_the_app_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    conf = _load(monkeypatch)

    assert conf["wsgi_app"] == "project_tracker:create_app()"
    assert conf["accesslog"] == "-"
    assert conf["control_socket_disable"] is True
