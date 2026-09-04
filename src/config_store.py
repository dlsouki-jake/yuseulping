"""사용자 설정(config.yaml)을 읽고 쓰는 역할."""
from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

DEFAULTS = {
    "channels": [],  # [{id, url, title, uploads_playlist_id}, ...]
    "poll_interval_hours": 1,
    "shorts_threshold_seconds": 180,
    "recommended_channel_limit": 5,
    "daily_generation_limit": 3,  # NotebookLM 일일 슬라이드 생성 한도 추정치 (공식 확인 안 됨, DESIGN.md 참고)
    "send_time": "08:00",
    "queue_policy": "carry_over",
    "email": {"address": "", "app_password": ""},
}


def load_config():
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
