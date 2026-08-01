from __future__ import annotations

from traderbot.platform_compat import get_platform, is_darwin, is_linux, is_windows


class TestGetPlatform:
    def test_returns_known_string(self) -> None:
        plat = get_platform()
        assert plat in ("Darwin", "Linux", "Windows")


class TestIsDarwin:
    def test_returns_bool(self) -> None:
        assert isinstance(is_darwin(), bool)


class TestIsLinux:
    def test_returns_bool(self) -> None:
        assert isinstance(is_linux(), bool)


class TestIsWindows:
    def test_returns_bool(self) -> None:
        assert isinstance(is_windows(), bool)
