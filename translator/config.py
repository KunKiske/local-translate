import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


APP_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "LocalTranslate"
CONFIG_FILE = APP_DIR / "settings.json"


@dataclass
class Settings:
    model_path: str = r"G:\Models\NLLB-600M"
    device: str = "cpu"
    compute_type: str = "int8"
    hotkey: str = "F1"
    naming_hotkey: str = "F2"
    dictionary_hotkey: str = "F3"
    reading_hotkey: str = "F4"
    debounce_ms: int = 550

    @classmethod
    def load(cls):
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Keep the user's previous selection shortcut when upgrading.
            data.setdefault("hotkey", data.get("selection_key", "F1"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(CONFIG_FILE)

