"""Per-user autostart setup for the wallpaper changer daemon."""

from __future__ import annotations

import os
import platform
import plistlib
import shlex
import sys
from pathlib import Path


APP_ID = "ru.course.wallpaperdesktop"
APP_TITLE = "Wallpaper Desktop"


class AutostartManager:
    """Enable or disable application startup with the operating system."""

    def __init__(self, python_executable: str | None = None, script_path: str | Path | None = None) -> None:
        self.python_executable = python_executable or sys.executable
        self.script_path = Path(script_path or sys.argv[0]).resolve()

    def is_enabled(self) -> bool:
        system = platform.system()
        if system == "Darwin":
            return self._macos_plist_path().exists()
        if system == "Windows":
            return self._windows_is_enabled()
        if system == "Linux":
            return self._linux_desktop_path().exists()
        return False

    def enable(self) -> None:
        system = platform.system()
        if system == "Darwin":
            self._enable_macos()
        elif system == "Windows":
            self._enable_windows()
        elif system == "Linux":
            self._enable_linux()
        else:
            raise RuntimeError(f"Автозапуск не поддерживается для ОС: {system}")

    def disable(self) -> None:
        system = platform.system()
        if system == "Darwin":
            self._macos_plist_path().unlink(missing_ok=True)
        elif system == "Windows":
            self._disable_windows()
        elif system == "Linux":
            self._linux_desktop_path().unlink(missing_ok=True)

    def _macos_plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

    def _enable_macos(self) -> None:
        path = self._macos_plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "Label": APP_ID,
            "ProgramArguments": [
                self.python_executable,
                str(self.script_path),
                "--daemon",
            ],
            "RunAtLoad": True,
            "KeepAlive": False,
            "StandardOutPath": str(Path.home() / "Library" / "Logs" / "WallpaperDesktop.log"),
            "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "WallpaperDesktop.log"),
        }
        with path.open("wb") as file:
            plistlib.dump(data, file)

    def _linux_desktop_path(self) -> Path:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "autostart" / "wallpaper-desktop.desktop"

    def _enable_linux(self) -> None:
        path = self._linux_desktop_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        command = f"{shlex.quote(self.python_executable)} {shlex.quote(str(self.script_path))} --daemon"
        path.write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=Application",
                    f"Name={APP_TITLE}",
                    f"Exec={command}",
                    "X-GNOME-Autostart-enabled=true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _windows_command(self) -> str:
        return f'"{self.python_executable}" "{self.script_path}" --daemon'

    def _windows_is_enabled(self) -> bool:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, APP_TITLE)
            return True
        except OSError:
            return False

    def _enable_windows(self) -> None:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_TITLE, 0, winreg.REG_SZ, self._windows_command())

    def _disable_windows(self) -> None:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_TITLE)
        except OSError:
            return