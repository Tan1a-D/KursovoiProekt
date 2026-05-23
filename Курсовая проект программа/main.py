"""Entry point for Wallpaper Desktop."""

from __future__ import annotations

import argparse
from pathlib import Path

from wallpaper_desktop.wallpaper_core import load_config, rotate_once, run_daemon, save_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automatic desktop wallpaper changer")
    parser.add_argument("--daemon", action="store_true", help="run in background mode without GUI")
    parser.add_argument("--change-now", action="store_true", help="change wallpaper once and exit")
    parser.add_argument("--config", type=Path, default=None, help="path to config.json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.daemon:
        run_daemon(args.config)
        return

    if args.change_now:
        config = load_config(args.config)
        rotate_once(config)
        save_config(config, args.config)
        return

    from wallpaper_desktop.app import run_gui

    run_gui()


if __name__ == "__main__":
    main()