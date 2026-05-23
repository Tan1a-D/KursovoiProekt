from pathlib import Path
import tempfile
import unittest

from wallpaper_desktop.wallpaper_core import (
    AppConfig,
    choose_next_image,
    import_images,
    is_rotation_due,
    is_supported_image,
    load_config,
    save_config,
)


class WallpaperCoreTests(unittest.TestCase):
    def test_supported_image_extensions(self) -> None:
        self.assertTrue(is_supported_image("photo.JPG"))
        self.assertTrue(is_supported_image("wallpaper.webp"))
        self.assertFalse(is_supported_image("notes.txt"))

    def test_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            config_path = Path(raw_dir) / "config.json"
            config = AppConfig(image_paths=["/tmp/a.jpg"], interval_seconds=60, order="random")
            save_config(config, config_path)
            loaded = load_config(config_path)
            self.assertEqual(loaded.image_paths, ["/tmp/a.jpg"])
            self.assertEqual(loaded.interval_seconds, 60)
            self.assertEqual(loaded.order, "random")

    def test_choose_next_image_sequential(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            first = Path(raw_dir) / "first.jpg"
            second = Path(raw_dir) / "second.jpg"
            first.write_bytes(b"image")
            second.write_bytes(b"image")
            config = AppConfig(image_paths=[str(first), str(second)], order="sequential")

            self.assertEqual(choose_next_image(config), str(first))
            self.assertEqual(choose_next_image(config), str(second))
            self.assertEqual(choose_next_image(config), str(first))

    def test_import_images_copies_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            source_dir = Path(raw_dir) / "source"
            target_dir = Path(raw_dir) / "target"
            source_dir.mkdir()
            image = source_dir / "photo.png"
            text = source_dir / "file.txt"
            image.write_bytes(b"image")
            text.write_text("not image", encoding="utf-8")

            imported = import_images([image, text], target_dir)
            self.assertEqual(len(imported), 1)
            self.assertTrue(Path(imported[0]).exists())
            self.assertEqual(Path(imported[0]).suffix, ".png")

    def test_rotation_due_without_previous_change(self) -> None:
        self.assertTrue(is_rotation_due(AppConfig()))


if __name__ == "__main__":
    unittest.main()