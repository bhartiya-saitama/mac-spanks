import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List


def _app_support_dir(app_name: str = "Spank Detector") -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, "Library", "Application Support", app_name)


def _bundled_resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(__file__)
    return os.path.join(base, relative_path)


@dataclass
class DefaultValues:
    threshold: float = 0.7
    cooldown: float = 0.4
    sleep_time: float = 1.0
    hit_sound_list: List[str] = field(default_factory=list)


@dataclass
class ActiveValues:
    threshold: float = 0.7
    cooldown: float = 0.4
    sleep_time: float = 1.0
    hit_sound: str = ""


class ConfigManager:
    """
    Persistent config:
    - Bundled src/config.json is treated as DEFAULTS.
    - On first run, copy bundled config.json into:
      ~/Library/Application Support/Spank Detector/config.json
    - From then on, always read/write that user config.
    """

    def __init__(self, config_path: str | None = None, app_name: str = "Spank Detector"):
        self.app_name = app_name

        # user config path (persistent)
        support = _app_support_dir(app_name)
        os.makedirs(support, exist_ok=True)
        self.user_config_path = os.path.join(support, "config.json")

        # bundled default config location
        # If caller passes a config_path, treat that as the default file in dev.
        if config_path:
            self.bundled_default = os.path.abspath(config_path)
        else:
            self.bundled_default = _bundled_resource_path("config.json")

        # ensure user config exists
        if not os.path.exists(self.user_config_path):
            self._seed_user_config()

        self._config: Dict[str, Any] = {}
        self.reload()

    def _seed_user_config(self):
        support = os.path.dirname(self.user_config_path)

        # 1. Copy bundled sample sound to App Support for a stable path
        bundled_sound = _bundled_resource_path("faah_sound.mp3")
        stable_sound = os.path.join(support, "faah_sound.mp3")
        if os.path.exists(bundled_sound) and not os.path.exists(stable_sound):
            try:
                shutil.copyfile(bundled_sound, stable_sound)
            except Exception:
                stable_sound = ""
        elif not os.path.exists(stable_sound):
            stable_sound = ""

        # 2. Read bundled config.json for default numeric values + theme
        bundled_cfg = {}
        try:
            if os.path.exists(self.bundled_default):
                with open(self.bundled_default, "r") as f:
                    bundled_cfg = json.load(f)
        except Exception:
            pass

        dv = bundled_cfg.get("default_values", {})
        av = bundled_cfg.get("active_values", {})
        sound_list = [stable_sound] if stable_sound else []

        # 3. Write user config with stable sound path baked in
        config = {
            "active_values": {
                "threshold": av.get("threshold", 0.7),
                "cooldown": av.get("cooldown", 0.4),
                "sleep_time": av.get("sleep_time", 1.0),
                "hit_sound": stable_sound,
            },
            "default_values": {
                "threshold": dv.get("threshold", 0.7),
                "cooldown": dv.get("cooldown", 0.4),
                "sleep_time": dv.get("sleep_time", 1.0),
                "hit_sound_list": sound_list,
            },
            "ui": bundled_cfg.get("ui", {"theme": "darkly"}),
        }
        with open(self.user_config_path, "w") as f:
            json.dump(config, f, indent=4)

    def reload(self):
        try:
            with open(self.user_config_path, "r") as f:
                self._config = json.load(f)
        except Exception:
            self._config = {}

    def save(self):
        tmp = self.user_config_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._config, f, indent=4)
        os.replace(tmp, self.user_config_path)

    # ---- UI section helpers (theme persistence) ----
    def set_ui_theme(self, theme: str):
        self._config.setdefault("ui", {})
        self._config["ui"]["theme"] = theme
        self.save()

    def get_ui_theme(self, default: str = "darkly") -> str:
        return self._config.get("ui", {}).get("theme", default)

    # ---- Values accessors returning objects ----
    def get_default_values(self) -> DefaultValues:
        dv = self._config.get("default_values", {}) or {}
        return DefaultValues(
            threshold=float(dv.get("threshold", 0.7)),
            cooldown=float(dv.get("cooldown", 0.4)),
            sleep_time=float(dv.get("sleep_time", 1.0)),
            hit_sound_list=list(dv.get("hit_sound_list", []) or []),
        )

    def get_active_values(self) -> ActiveValues:
        av = self._config.get("active_values", {}) or {}
        return ActiveValues(
            threshold=float(av.get("threshold", 0.7)),
            cooldown=float(av.get("cooldown", 0.4)),
            sleep_time=float(av.get("sleep_time", 1.0)),
            hit_sound=str(av.get("hit_sound", "")),
        )

    # ---- Mutators used by your GUI ----
    def set_active_sound(self, path: str):
        self._config.setdefault("active_values", {})
        self._config["active_values"]["hit_sound"] = path
        self.save()

    def add_sound(self, path: str):
        self._config.setdefault("default_values", {})
        lst = self._config["default_values"].setdefault("hit_sound_list", [])
        if path not in lst:
            lst.append(path)

        self._config.setdefault("active_values", {})
        self._config["active_values"]["hit_sound"] = path
        self.save()

    def remove_sound(self, path: str):
        dv = self._config.setdefault("default_values", {})
        lst = dv.setdefault("hit_sound_list", [])
        if path in lst:
            lst.remove(path)

        av = self._config.setdefault("active_values", {})
        if av.get("hit_sound") == path:
            av["hit_sound"] = lst[0] if lst else ""
        self.save()

    def set_active_advanced(self, threshold: float, cooldown: float, sleep_time: float):
        av = self._config.setdefault("active_values", {})
        av["threshold"] = float(threshold)
        av["cooldown"] = float(cooldown)
        av["sleep_time"] = float(sleep_time)
        self.save()

    def reset_active_advanced_to_defaults(self):
        dv = self._config.get("default_values", {}) or {}
        av = self._config.setdefault("active_values", {})

        av["threshold"] = float(dv.get("threshold", 0.7))
        av["cooldown"] = float(dv.get("cooldown", 0.4))
        av["sleep_time"] = float(dv.get("sleep_time", 1.0))
        self.save()