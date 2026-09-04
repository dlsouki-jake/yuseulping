"""신규 업로드 감지 + 쇼츠 필터링 + 대기열 관리 + 슬라이드 생성 파이프라인.

실행: python src/watcher.py  (컴퓨터 시작 시 자동 실행 + 이후 반복 실행되도록 등록해서 씀)

"따라잡기" 방식: 매번 실행될 때마다 "마지막 확인 후 설정된 시간이 지났는지"를
스스로 확인해서, 지났을 때만 실제로 확인 작업을 한다. `--force`를 주면 이 판단을
건너뛰고 무조건 확인한다 (테스트/수동 실행용).

대기열 정책: NotebookLM의 일일 생성 한도(추정치, config의 daily_generation_limit)를
넘으면 나머지는 대기열에 쌓인다. queue_policy가 carry_over면 다음 실행 때 이어서
처리하고, daily_drop이면 오늘 처리 못 한 건 이월하지 않고 버린다. 생성 실패(예: 자막
없음)는 정책과 무관하게 1회만 재시도하고, 그래도 실패하면 최종 실패로 기록한다.
"""
import asyncio
import sys
from datetime import datetime

from config_store import load_config
from recent_uploads import fetch_recent_videos, fetch_duration_seconds
from state_store import (
    load_state,
    save_state,
    is_seen,
    should_check_now,
    mark_checked_now,
    remaining_daily_budget,
    record_generation,
    expire_stale_queue_items,
    mark_login_needed,
)
import sender
import slides


def handle_login_expired(config):
    """로그인 만료를 상태에 기록하고, 가능하면 이메일로도 알린다."""
    mark_login_needed()
    email_address = config["email"]["address"]
    app_password = config["email"]["app_password"]
    if not email_address or not app_password:
        return
    try:
        sender.send_alert_email(
            email_address,
            app_password,
            "NotebookLM 로그인이 풀렸어요",
            "슬라이드 생성이 중단됐어요. 아래 명령을 실행해서 다시 로그인해주세요.\n\n"
            "python scripts/notebooklm_login.py\n\n"
            "다시 로그인하면 밀려있던 영상들이 이어서 처리돼요.",
        )
    except Exception as e:
        print(f"[알림 메일 발송 실패] {e}")


def check_new_uploads():
    """등록된 채널에서 신규 롱폼 영상을 찾아 대기열(state.queued)에 추가한다."""
    config = load_config()
    threshold = config["shorts_threshold_seconds"]
    state = load_state()
    now = datetime.now().isoformat()

    found = 0
    for ch in config["channels"]:
        try:
            recent = fetch_recent_videos(ch["url"])
        except Exception as e:
            print(f"[감지 실패] {ch['title']}: {e}")
            continue

        for video in recent:
            if is_seen(video["video_id"]):
                continue

            try:
                duration = fetch_duration_seconds(video["url"])
            except Exception as e:
                print(f"[재생시간 조회 실패, 스킵] {video['title']}: {e}")
                continue

            if duration is not None and duration <= threshold:
                print(f"[쇼츠 제외] {video['title']} ({duration}초)")
                state["seen_video_ids"].append(video["video_id"])
                continue

            print(f"[신규 롱폼 발견 → 대기열에 추가] {ch['title']} · {video['title']} ({duration}초)")
            state["seen_video_ids"].append(video["video_id"])
            state["queued"].append(
                {**video, "channel_title": ch["title"], "queued_at": now, "retry_count": 0}
            )
            found += 1

    save_state(state)
    return found


async def process_queue():
    """대기열에서 오늘 남은 한도만큼 슬라이드를 생성한다."""
    if not slides.is_logged_in():
        print("\nNotebookLM에 로그인돼 있지 않아요.")
        print("먼저 이 명령을 한 번 실행해주세요: python scripts/notebooklm_login.py")
        return

    config = load_config()
    state = load_state()
    queue = state.get("queued", [])

    if not queue:
        print("대기열이 비어있어요.")
        return

    budget = remaining_daily_budget(config["daily_generation_limit"])
    if budget <= 0:
        print(f"오늘 생성 한도({config['daily_generation_limit']}개, 추정치)를 이미 다 썼어요. 다음에 이어서 처리할게요.")
        return

    to_process, remaining = queue[:budget], queue[budget:]
    print(f"\n대기열 {len(queue)}개 중 {len(to_process)}개를 지금 처리할게요.")

    retry_later = []
    for i, video in enumerate(to_process):
        print(f"\n[슬라이드 생성 시작] {video['title']}")
        try:
            pdf_path = await slides.generate_slide_deck(video["title"], video["url"])
        except slides.NotebookLMAuthError as e:
            print(f"[로그인 만료 감지] {e}")
            handle_login_expired(config)
            # 이번에 처리 못 한 것들(지금 것 포함)은 그대로 큐에 남겨서 재로그인 후 이어서 처리
            not_yet_processed = to_process[i:]
            s = load_state()
            s["queued"] = not_yet_processed + retry_later + remaining
            save_state(s)
            return
        except Exception as e:
            if video.get("retry_count", 0) < 1:
                print(f"[슬라이드 생성 실패, 다음 번에 1회 재시도] {video['title']}: {e}")
                retry_later.append({**video, "retry_count": video.get("retry_count", 0) + 1})
            else:
                print(f"[슬라이드 생성 최종 실패] {video['title']}: {e}")
                s = load_state()
                s["failed"].append({**video, "reason": str(e)})
                save_state(s)
            continue

        print(f"[슬라이드 생성 완료] {pdf_path}")
        record_generation()
        s = load_state()
        clean_video = {k: v for k, v in video.items() if k not in ("queued_at", "retry_count")}
        s["pending"].append({**clean_video, "pdf_path": pdf_path})
        save_state(s)

    # 처리 못 한(예산 초과) 영상들: 정책에 따라 이월하거나 버림
    s = load_state()
    if config["queue_policy"] == "carry_over":
        s["queued"] = retry_later + remaining
    else:  # daily_drop — 실패 재시도 대상만 남기고, 예산 초과로 못 한 건 이월 없이 버림
        if remaining:
            print(f"[정책: 당일만 처리] 오늘 못 한 {len(remaining)}개는 이월하지 않고 넘어가요.")
        s["queued"] = retry_later
    save_state(s)


def main():
    force = "--force" in sys.argv
    config = load_config()

    expired = expire_stale_queue_items()
    if expired:
        print(f"[대기열 정리] 3일 넘게 대기 중이던 {expired}개 항목을 정리했어요.")

    if not force and not should_check_now(config["poll_interval_hours"]):
        print(f"아직 확인할 시간이 안 됐어요 (확인 주기: {config['poll_interval_hours']}시간). 건너뜁니다.")
    else:
        found = check_new_uploads()
        mark_checked_now()
        if found:
            print(f"\n총 {found}개의 신규 롱폼 영상을 대기열에 추가했어요.")

    asyncio.run(process_queue())


if __name__ == "__main__":
    main()
