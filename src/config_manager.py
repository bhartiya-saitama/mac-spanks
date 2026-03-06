# config_manager.py
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ActiveValues:
    threshold: float
    cooldown: float
    sleep_time: float
    hit_sound: str


@dataclass
class DefaultValues:
    threshold: float
    cooldown: float
    sleep_time: float
    hit_sound_list: List[str]


class ConfigManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"config.json not found: {self.config_path}")
        with open(self.config_path, "r") as f:
            self._config = json.load(f)

        self._config.setdefault("active_values", {})
        self._config.setdefault("default_values", {})
        self._config["default_values"].setdefault("hit_sound_list", [])

        dv = self._config["default_values"]
        av = self._config["active_values"]

        av.setdefault("threshold", dv.get("threshold", 0.7))
        av.setdefault("cooldown", dv.get("cooldown", 0.4))
        av.setdefault("sleep_time", dv.get("sleep_time", 1.0))

        if "hit_sound" not in av:
            av["hit_sound"] = dv["hit_sound_list"][0] if dv["hit_sound_list"] else ""

        self.save()

    def save(self) -> None:
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=4)

    def get_default_values(self) -> DefaultValues:
        dv = self._config["default_values"]
        return DefaultValues(
            threshold=float(dv.get("threshold", 0.7)),
            cooldown=float(dv.get("cooldown", 0.4)),
            sleep_time=float(dv.get("sleep_time", 1.0)),
            hit_sound_list=list(dv.get("hit_sound_list", [])),
        )

    def get_active_values(self) -> ActiveValues:
        av = self._config["active_values"]
        return ActiveValues(
            threshold=float(av.get("threshold", 0.7)),
            cooldown=float(av.get("cooldown", 0.4)),
            sleep_time=float(av.get("sleep_time", 1.0)),
            hit_sound=str(av.get("hit_sound", "")),
        )

    def set_active_sound(self, sound_path: str) -> None:
        self._config["active_values"]["hit_sound"] = sound_path
        self.save()

    def add_sound(self, sound_path: str) -> None:
        dv_list = self._config["default_values"].setdefault("hit_sound_list", [])
        if sound_path not in dv_list:
            dv_list.append(sound_path)

        self._config["active_values"]["hit_sound"] = sound_path
        self.save()

    def remove_sound(self, sound_path: str) -> None:
        """
        Remove sound from defaults list. If it was active, set active to first remaining or ''.
        """
        dv_list = self._config["default_values"].setdefault("hit_sound_list", [])
        if sound_path in dv_list:
            dv_list.remove(sound_path)

        av = self._config["active_values"]
        if av.get("hit_sound") == sound_path:
            av["hit_sound"] = dv_list[0] if dv_list else ""

        self.save()

    def set_active_advanced(self, threshold: float, cooldown: float, sleep_time: float) -> None:
        if threshold < 0 or cooldown < 0 or sleep_time <= 0:
            raise ValueError("threshold>=0, cooldown>=0, sleep_time>0 required")

        av = self._config["active_values"]
        av["threshold"] = round(float(threshold), 2)
        av["cooldown"] = round(float(cooldown), 2)
        av["sleep_time"] = round(float(sleep_time), 2)
        self.save()

    def reset_active_advanced_to_defaults(self) -> None:
        dv = self._config["default_values"]
        self.set_active_advanced(
            threshold=float(dv.get("threshold", 0.7)),
            cooldown=float(dv.get("cooldown", 0.4)),
            sleep_time=float(dv.get("sleep_time", 1.0)),
        )