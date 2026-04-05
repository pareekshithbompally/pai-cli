"""Standard-library path helpers for pai."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "pai"


def _xdg_home(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else fallback


def xdg_cache_home() -> Path:
    return _xdg_home("XDG_CACHE_HOME", Path.home() / ".cache")


def xdg_config_home() -> Path:
    return _xdg_home("XDG_CONFIG_HOME", Path.home() / ".config")


def xdg_data_home() -> Path:
    return _xdg_home("XDG_DATA_HOME", Path.home() / ".local" / "share")


def app_cache_dir() -> Path:
    return xdg_cache_home() / APP_NAME


def app_config_dir() -> Path:
    return xdg_config_home() / APP_NAME


def app_data_dir() -> Path:
    return xdg_data_home() / APP_NAME


def app_cache_path(*parts: str) -> Path:
    return app_cache_dir().joinpath(*parts)


def app_config_path(*parts: str) -> Path:
    return app_config_dir().joinpath(*parts)


def app_data_path(*parts: str) -> Path:
    return app_data_dir().joinpath(*parts)


def hidden_tool_dir(name: str) -> Path:
    return Path.home() / f".{name}"
