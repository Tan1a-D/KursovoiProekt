"""Graphical interface for Wallpaper Desktop."""

from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .autostart import AutostartManager
from .wallpaper_core import (
    APP_NAME,
    INTERVAL_OPTIONS,
    AppConfig,
    collect_images_from_folder,
    get_config_path,
    get_photos_dir,
    import_images,
    load_config,
    rotate_once,
    save_config,
)


class WallpaperApp(tk.Tk):
    """Main window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(760, 460)

        self.config_path = get_config_path()
        self.photos_dir = get_photos_dir()
        self.config_data: AppConfig = load_config(self.config_path)
        self.autostart = AutostartManager(
            python_executable=sys.executable,
            script_path=Path(sys.argv[0]).resolve(),
        )
        self.after_id: str | None = None
        self.is_running = False

        self.interval_var = tk.StringVar(value=self._label_for_interval(self.config_data.interval_seconds))
        self.order_var = tk.StringVar(value="Случайно" if self.config_data.order == "random" else "По порядку")
        self.autostart_var = tk.BooleanVar(value=self.config_data.run_on_startup or self.autostart.is_enabled())
        self.status_var = tk.StringVar(value="Готово")

        self._build_menu()
        self._build_layout()
        self._refresh_image_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Добавить фотографии", command=self.add_files)
        file_menu.add_command(label="Добавить папку", command=self.add_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)
        menu.add_cascade(label="Файл", menu=file_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Справка", command=self.show_help)
        help_menu.add_command(label="О программе", command=self.show_about)
        menu.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=menu)

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        title = ttk.Label(root, text="Обои рабочего стола", font=("Arial", 18, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        list_frame = ttk.LabelFrame(root, text="Фотографии", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.image_list = tk.Listbox(list_frame, height=14, activestyle="dotbox")
        self.image_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.image_list.configure(yscrollcommand=scrollbar.set)

        list_buttons = ttk.Frame(list_frame)
        list_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        list_buttons.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(list_buttons, text="Добавить фото", command=self.add_files).grid(row=0, column=0, sticky="ew", 
padx=(0, 6))
        ttk.Button(list_buttons, text="Добавить папку", command=self.add_folder).grid(row=0, column=1, sticky="ew", 
padx=6)
        ttk.Button(list_buttons, text="Удалить", command=self.remove_selected).grid(row=0, column=2, sticky="ew", 
padx=(6, 0))

        controls = ttk.LabelFrame(root, text="Настройки", padding=14)
        controls.grid(row=1, column=1, sticky="nsew")
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Интервал").grid(row=0, column=0, sticky="w", pady=(0, 8))
        interval_box = ttk.Combobox(
            controls,
            textvariable=self.interval_var,
            values=list(INTERVAL_OPTIONS.keys()),
            state="readonly",
        )
        interval_box.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        interval_box.bind("<<ComboboxSelected>>", lambda _event: self.save_settings())

        ttk.Label(controls, text="Порядок").grid(row=1, column=0, sticky="w", pady=8)
        order_box = ttk.Combobox(
            controls,
            textvariable=self.order_var,
            values=["По порядку", "Случайно"],
            state="readonly",
        )
        order_box.grid(row=1, column=1, sticky="ew", pady=8)
        order_box.bind("<<ComboboxSelected>>", lambda _event: self.save_settings())

        autostart_check = ttk.Checkbutton(
            controls,
            text="Запускать вместе с системой",
            variable=self.autostart_var,
            command=self.toggle_autostart,
        )
        autostart_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=8)

        actions = ttk.Frame(controls)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        actions.columnconfigure((0, 1), weight=1)
        ttk.Button(actions, text="Сменить сейчас", command=self.change_now).grid(row=0, column=0, sticky="ew", 
padx=(0, 6))
        self.start_button = ttk.Button(actions, text="Старт", command=self.toggle_rotation)
        self.start_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ttk.Separator(root).grid(row=2, column=0, columnspan=2, sticky="ew", pady=12)
        status = ttk.Label(root, textvariable=self.status_var, anchor="w")
        status.grid(row=3, column=0, columnspan=2, sticky="ew")

    def _label_for_interval(self, seconds: int) -> str:
        for label, value in INTERVAL_OPTIONS.items():
            if value == seconds:
                return label
        return "1 день"

    def _refresh_image_list(self) -> None:
        self.image_list.delete(0, tk.END)
        for path in self.config_data.image_paths:
            self.image_list.insert(tk.END, Path(path).name)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите фотографии",
            filetypes=[
                ("Изображения", "*.jpg *.jpeg *.png *.bmp *.gif *.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        self._add_paths(paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Выберите папку с фотографиями")
        if folder:
            self._add_paths(collect_images_from_folder(folder))

    def _add_paths(self, paths: tuple[str, ...] | list[Path]) -> None:
        imported = import_images(paths, self.photos_dir, self.config_data.image_paths)
        if not imported:
            self.status_var.set("Подходящие изображения не найдены")
            return

        self.config_data.image_paths.extend(imported)
        self.save_settings()
        self._refresh_image_list()
        self.status_var.set(f"Добавлено изображений: {len(imported)}")

    def remove_selected(self) -> None:
        selected = list(self.image_list.curselection())
        if not selected:
            return

        for index in reversed(selected):
            del self.config_data.image_paths[index]
        if self.config_data.current_index >= len(self.config_data.image_paths):
            self.config_data.current_index = len(self.config_data.image_paths) - 1
        self.save_settings()
        self._refresh_image_list()
        self.status_var.set("Выбранные изображения удалены из списка")

    def save_settings(self) -> None:
        self.config_data.interval_seconds = INTERVAL_OPTIONS.get(self.interval_var.get(), 24 * 60 * 60)
        self.config_data.order = "random" if self.order_var.get() == "Случайно" else "sequential"
        self.config_data.run_on_startup = self.autostart_var.get()
        save_config(self.config_data, self.config_path)

    def toggle_autostart(self) -> None:
        try:
            if self.autostart_var.get():
                self.autostart.enable()
                self.status_var.set("Автозапуск включен")
            else:
                self.autostart.disable()
                self.status_var.set("Автозапуск выключен")
        except Exception as exc:
            self.autostart_var.set(False)
            messagebox.showerror("Автозапуск", f"Не удалось изменить автозапуск:\n{exc}")
        finally:
            self.save_settings()

    def change_now(self) -> bool:
        self.save_settings()
        try:
            image_path = rotate_once(self.config_data)
        except Exception as exc:
            messagebox.showerror("Смена обоев", f"Не удалось сменить обои:\n{exc}")
            self.status_var.set("Ошибка смены обоев")
            return False

        self.save_settings()
        self.status_var.set(f"Установлено: {Path(image_path).name}")
        return True

    def toggle_rotation(self) -> None:
        if self.is_running:
            self.stop_rotation()
        else:
            self.start_rotation()

    def start_rotation(self) -> None:
        if not self.config_data.image_paths:
            messagebox.showwarning("Нет фотографий", "Добавьте хотя бы одну фотографию.")
            return

        self.is_running = True
        self.start_button.configure(text="Стоп")
        self.status_var.set("Автоматическая смена включена")
        if not self.change_now():
            self.is_running = False
            self.start_button.configure(text="Старт")
            return
        self._schedule_next()

    def stop_rotation(self) -> None:
        self.is_running = False
        self.start_button.configure(text="Старт")
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        self.status_var.set("Автоматическая смена остановлена")

    def _schedule_next(self) -> None:
        if not self.is_running:
            return

        delay_ms = max(1, self.config_data.interval_seconds) * 1000
        self.after_id = self.after(delay_ms, self._scheduled_change)

    def _scheduled_change(self) -> None:
        if not self.is_running:
            return
        self.change_now()
        self._schedule_next()

    def show_help(self) -> None:
        messagebox.showinfo(
            "Справка",
            "1. Нажмите «Добавить фото» или «Добавить папку».\n"
            "2. Выберите интервал смены: 1 минута, 5 минут, 30 минут, 1 час или 1 день.\n"
            "3. Нажмите «Сменить сейчас» для ручной смены или «Старт» для автоматической.\n"
            "4. Флажок автозапуска включает фоновый режим при входе в систему.",
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "О программе",
            f"{APP_NAME} {__version__}\n"
            "Учебное приложение для автоматической смены обоев рабочего стола.",
        )

    def _on_close(self) -> None:
        self.stop_rotation()
        self.save_settings()
        self.destroy()


def run_gui() -> None:
    app = WallpaperApp()
    app.mainloop()