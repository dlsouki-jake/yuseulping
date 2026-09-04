"""처리 상태(이미 확인한 영상, 발송 대기함)를 저장하는 역할. config.yaml과는 분리된 운영용 파일."""
from datetime import datetime, date
from pathlib import Path
import yaml

STATE_DIR = Path(__file__).resolve().parent.parent / "config"
STATE_PATH = STATE_DIR / "state.yaml"

DEFAULTS = {
    "seen_video_ids": [],  # 이미 확인해서 처리(또는 스킵) 완료한 영상 ID 목록
    "pending": [],  # 슬라이드까지 만들었지만 아직 이메일로 발송 안 한 항목들 (발송 대기함)
    "failed": [],  # 자막 없음 등으로 최종 실패한 항목 (대시보드 표시용)
    "queued": [],  # 일일 생성 한도 초과로 아직 슬라이드를 못 만든 영상들 (queue_policy=carry_over일 때만 쌓임)
    "generated_date": None,  # 오늘 생성 개수를 세는 기준 날짜 (YYYY-MM-DD)
    "generated_count": 0,  # 그 날짜 기준으로 지금까지 만든 슬라이드 개수
    "last_checked_at": None,  # 신규 업로드를 마지막으로 확인한 시각 (ISO 문자열) — "따라잡기" 판단용
    "last_sent_at": None,  # 이메일을 마지막으로 발송한 날짜 (YYYY-MM-DD) — "따라잡기" 판단용
    "login_needed": False,  # NotebookLM 재로그인이 필요한 상태인지 (대시보드 배너 표시용)
}


def load_state():
    if not STATE_PATH.exists():
        return dict(DEFAULTS)
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False)


def mark_seen(video_id):
    state = load_state()
    if video_id not in state["seen_video_ids"]:
        state["seen_video_ids"].append(video_id)
        save_state(state)


def is_seen(video_id):
    state = load_state()
    return video_id in state["seen_video_ids"]


def should_check_now(poll_interval_hours):
    """마지막 확인 후 지정된 시간이 지났으면 True. 한 번도 확인 안 했으면 항상 True."""
    state = load_state()
    last = state.get("last_checked_at")
    if not last:
        return True
    elapsed_hours = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
    return elapsed_hours >= poll_interval_hours


def mark_checked_now():
    state = load_state()
    state["last_checked_at"] = datetime.now().isoformat()
    save_state(state)


def should_send_now(send_time):
    """오늘 아직 발송 안 했고, 지정한 발송 시각이 지났으면 True."""
    state = load_state()
    today = date.today().isoformat()
    if state.get("last_sent_at") == today:
        return False
    send_hour, send_minute = (int(x) for x in send_time.split(":"))
    now = datetime.now()
    return (now.hour, now.minute) >= (send_hour, send_minute)


def mark_sent_today():
    state = load_state()
    state["last_sent_at"] = date.today().isoformat()
    save_state(state)


def remaining_daily_budget(daily_limit):
    """오늘 슬라이드를 몇 개 더 만들 수 있는지 (NotebookLM 일일 생성 한도 대응).

    daily_limit은 확인된 공식 수치가 아니라 추정치라 설정에서 조정 가능함 (DESIGN.md 참고).
    """
    state = load_state()
    today = date.today().isoformat()
    if state.get("generated_date") != today:
        return daily_limit  # 날짜가 바뀌었으면 새로 리셋된 것으로 취급
    return max(0, daily_limit - state.get("generated_count", 0))


def record_generation():
    """슬라이드 하나를 성공적으로 만들었을 때 오늘 카운트를 1 늘림."""
    state = load_state()
    today = date.today().isoformat()
    if state.get("generated_date") != today:
        state["generated_date"] = today
        state["generated_count"] = 0
    state["generated_count"] += 1
    save_state(state)


def mark_login_needed():
    state = load_state()
    state["login_needed"] = True
    save_state(state)


def clear_login_needed():
    state = load_state()
    if state.get("login_needed"):
        state["login_needed"] = False
        save_state(state)


def expire_stale_queue_items(max_days=3):
    """대기열(queued)에 너무 오래(기본 3일) 머문 항목을 정리한다."""
    state = load_state()
    cutoff = datetime.now().timestamp() - max_days * 86400
    before = len(state.get("queued", []))
    state["queued"] = [
        item for item in state.get("queued", [])
        if datetime.fromisoformat(item["queued_at"]).timestamp() >= cutoff
    ]
    removed = before - len(state["queued"])
    if removed:
        save_state(state)
    return removed
