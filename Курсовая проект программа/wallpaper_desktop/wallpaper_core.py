"""Core logic for the desktop wallpaper changer.

The module is deliberately independent from the graphical interface. This
keeps the application easier to test and makes the course project structure
closer to the ESPD recommendations: user interface, processing logic and
system interaction are separated.
"""

from __future__ import annotations

import json
import os
import platform
import random
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


APP_NAME = "Wallpaper Desktop"
CONFIG_FILE_NAME = "config.json"
PHOTOS_DIR_NAME = "photos"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
}

INTERVAL_OPTIONS = {
    "1 минута": 60,
    "5 минут": 5 * 60,
    "30 минут": 30 * 60,
    "1 час": 60 * 60,
    "1 день": 24 * 60 * 60,
}


@dataclass
class AppConfig:
    """Persistent application settings."""

    image_paths: list[str] = field(default_factory=list)
    interval_seconds: int = 24 * 60 * 60
    order: str = "sequential"
    current_index: int = -1
    run_on_startup: bool = False
    last_changed_at: str = ""
    last_image_path: str = ""


def get_app_data_dir() -> Path:
    """Return a writable per-user data directory for the application."""

    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "WallpaperDesktop"
    if system == "Windows":
        base = os.environ.get("APPDATA")
        return Path(base) / "WallpaperDesktop" if base else Path.home() / "WallpaperDesktop"

    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) / "wallpaper-desktop" if base else Path.home() / ".config" / "wallpaper-desktop"


def get_config_path(data_dir: Path | None = None) -> Path:
    """Return the path to the JSON settings file."""

    return (data_dir or get_app_data_dir()) / CONFIG_FILE_NAME


def get_photos_dir(data_dir: Path | None = None) -> Path:
    """Return the folder where imported user photos are copied."""

    return (data_dir or get_app_data_dir()) / PHOTOS_DIR_NAME


def load_config(path: Path | None = None) -> AppConfig:
    """Load application settings from JSON.

    If the file is absent or damaged, default settings are returned. This is a
    reliability measure: a broken config must not prevent the application from
    opening.
    """

    path = path or get_config_path()
    if not path.exists():
        return AppConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppConfig()

    config = AppConfig()
    for field_name in asdict(config):
        if field_name in data:
            setattr(config, field_name, data[field_name])

    config.image_paths = [str(Path(item)) for item in config.image_paths if item]
    if config.interval_seconds <= 0:
        config.interval_seconds = 24 * 60 * 60
    if config.order not in {"sequential", "random"}:
        config.order = "sequential"
    return config


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Save application settings to JSON."""

    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_supported_image(path: str | Path) -> bool:
    """Check whether a file extension can be used as a wallpaper image."""

    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def collect_images_from_folder(folder: str | Path) -> list[Path]:
    """Collect supported images from a folder recursively."""

    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return []

    images: list[Path] = []
    for item in folder_path.rglob("*"):
        if item.is_file() and is_supported_image(item):
            images.append(item)
    return sorted(images, key=lambda item: str(item).lower())


def _unique_destination(source: Path, target_dir: Path) -> Path:
    """Build a non-conflicting destination path for an imported image."""

    target = target_dir / source.name
    if not target.exists():
        return target

    stem = source.stem
    suffix = source.suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def import_images(
    paths: Iterable[str | Path],
    photos_dir: Path | None = None,
    existing_paths: Iterable[str] | None = None,
) -> list[str]:
    """Copy selected images to the application photo library.

    Returning absolute paths makes wallpaper setting predictable even when the
    program is started by the OS at login.
    """

    photos_dir = photos_dir or get_photos_dir()
    photos_dir.mkdir(parents=True, exist_ok=True)
    existing = {str(Path(item).resolve()) for item in existing_paths or []}
    imported: list[str] = []

    for raw_path in paths:
        source = Path(raw_path).expanduser()
        if not source.exists() or not source.is_file() or not is_supported_image(source):
            continue

        destination = _unique_destination(source, photos_dir)
        shutil.copy2(source, destination)
        resolved = str(destination.resolve())
        if resolved not in existing:
            imported.append(resolved)
            existing.add(resolved)

    return imported


def remove_missing_images(config: AppConfig) -> None:
    """Delete image paths that no longer exist on disk from the config."""

    config.image_paths = [path for path in config.image_paths if Path(path).exists()]
    if config.current_index >= len(config.image_paths):
        config.current_index = len(config.image_paths) - 1


def choose_next_image(config: AppConfig) -> str:
    """Choose the next image according to the configured order."""

    remove_missing_images(config)
    if not config.image_paths:
        raise ValueError("В список не добавлены изображения.")

    if config.order == "random":
        if len(config.image_paths) == 1:
            config.current_index = 0
        else:
            candidates = list(range(len(config.image_paths)))
            if 0 <= config.current_index < len(candidates):
                candidates.remove(config.current_index)
            config.current_index = random.choice(candidates)
    else:
        config.current_index = (config.current_index + 1) % len(config.image_paths)

    return config.image_paths[config.current_index]


def rotate_once(config: AppConfig) -> str:
    """Select and apply the next wallpaper image."""

    image_path = choose_next_image(config)
    set_wallpaper(image_path)
    config.last_changed_at = datetime.now().isoformat(timespec="seconds")
    config.last_image_path = image_path
    return image_path


def is_rotation_due(config: AppConfig, now: float | None = None) -> bool:
    """Return True when the configured interval has elapsed."""

    if not config.last_changed_at:
        return True

    try:
        last_change = datetime.fromisoformat(config.last_changed_at).timestamp()
    except ValueError:
        return True

    return (now or time.time()) - last_change >= config.interval_seconds


def run_daemon(config_path: Path | None = None) -> None:
    """Run wallpaper rotation without opening the graphical interface."""

    while True:
        config = load_config(config_path)
        try:
            if is_rotation_due(config):
                rotate_once(config)
                save_config(config, config_path)
        except Exception:
            # The daemon must keep running even after a temporary OS error.
            pass

        sleep_seconds = max(10, min(60, int(config.interval_seconds / 4)))
        time.sleep(sleep_seconds)


def set_wallpaper(image_path: str | Path) -> None:
    """Set a desktop wallpaper using the current operating system API."""

    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    system = platform.system()
    if system == "Darwin":
        _set_wallpaper_macos(path)
    elif system == "Windows":
        _set_wallpaper_windows(path)
    elif system == "Linux":
        _set_wallpaper_linux(path)
    else:
        raise RuntimeError(f"Операционная система не поддерживается: {system}")


def _applescript_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _set_wallpaper_macos(path: Path) -> None:
    script = (
        "tell application \"System Events\" "
        f"to set picture of every desktop to POSIX file {_applescript_quote(str(path))}"
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "неизвестная ошибка macOS"
        raise RuntimeError(message)


def _set_wallpaper_windows(path: Path) -> None:
    import ctypes

    spi_set_desktop_wallpaper = 20
    spif_update_ini_file = 0x01
    spif_send_change = 0x02
    result = ctypes.windll.user32.SystemParametersInfoW(
        spi_set_desktop_wallpaper,
        0,
        str(path),
        spif_update_ini_file | spif_send_change,
    )
    if not result:
        raise ctypes.WinError()


def _set_wallpaper_linux(path: Path) -> None:
    uri = path.as_uri()
    errors: list[str] = []

    commands = []
    if shutil.which("gsettings"):
        commands.append(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
        commands.append(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])
    if shutil.which("plasma-apply-wallpaperimage"):
        commands.append(["plasma-apply-wallpaperimage", str(path)])
    if shutil.which("feh"):
        commands.append(["feh", "--bg-fill", str(path)])

    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return
        errors.append(result.stderr.strip() or result.stdout.strip() or "команда завершилась ошибкой")

    details = "; ".join(errors) if errors else "не найдена поддерживаемая команда смены обоев"
    raise RuntimeError(f"Не удалось сменить обои в Linux: {details}")