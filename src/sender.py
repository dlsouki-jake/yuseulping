"""이메일 발송 담당 (Gmail 앱 비밀번호 + SMTP, OAuth 불필요).

실행: python src/sender.py (watcher.py와 같이 "따라잡기" 방식으로 반복 실행되도록 등록해서 씀)

"따라잡기" 방식: 오늘 지정한 발송 시각이 지났는데 아직 오늘 발송을 안 했으면 지금 발송한다.
컴퓨터가 그 시각에 꺼져 있었어도, 다음에 켜지면 알아서 그날치를 보낸다.
`--force`를 주면 이 판단을 건너뛰고 무조건 발송을 시도한다 (테스트/수동 실행용).

역할:
- 발송 대기함(state.yaml의 pending)에 쌓인 항목이 없으면 아무것도 하지 않는다
- 있으면 PDF를 첨부한 이메일로 발송한다
- Gmail은 메시지 크기 제한(약 25MB, 첨부파일 인코딩 포함)이 있어서, 실측 결과 NotebookLM
  슬라이드 PDF 하나가 10~20MB까지 나올 수 있었다. 여러 개를 한 통에 몰아 보내면 제한을
  넘어 발송 자체가 거부될 수 있어서, 총 용량이 안전선을 넘으면 여러 통으로 나눠 보낸다.
- 발송 성공한 항목만 대기함에서 빠지고, 실패한 항목은 남아서 다음 실행 때 다시 시도된다
"""
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from config_store import load_config
from state_store import load_state, save_state, should_send_now, mark_sent_today

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Gmail의 메시지 크기 제한은 인코딩 후 기준 약 25MB. Base64 인코딩은 원본보다 약 37% 커지고
# 메일 본문/헤더도 약간의 여유가 필요해서, 원본 파일 기준으로는 이보다 낮게 잡아야 안전하다.
SAFE_BATCH_BYTES = 18 * 1024 * 1024
TITLE_ABBREV_LENGTH = 20


def abbreviate_title(title, max_length=TITLE_ABBREV_LENGTH):
    if len(title) <= max_length:
        return title
    return title[:max_length] + "…"


def batch_items_by_size(items):
    """총 첨부 용량이 안전선을 넘지 않도록 항목들을 여러 묶음으로 나눈다."""
    batches = []
    current_batch = []
    current_size = 0

    for item in items:
        pdf_path = Path(item["pdf_path"])
        if not pdf_path.exists():
            continue
        size = pdf_path.stat().st_size
        if current_batch and current_size + size > SAFE_BATCH_BYTES:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        current_batch.append(item)
        current_size += size

    if current_batch:
        batches.append(current_batch)

    return batches


def build_subject(items):
    first = items[0]
    title = f"{first['channel_title']} {abbreviate_title(first['title'])} 영상 요약"
    if len(items) == 1:
        return f"[유슬핑] {title} 1건"
    return f"[유슬핑] {title} 외 {len(items) - 1}건"


def build_digest_email(sender_address, items):
    msg = EmailMessage()
    msg["Subject"] = build_subject(items)
    msg["From"] = sender_address
    msg["To"] = sender_address

    lines = ["오늘 새로 만들어진 슬라이드 요약이에요.\n"]
    for item in items:
        lines.append(f"- {item['channel_title']} · {item['title']}")
        lines.append(f"  {item['url']}")
    body = "\n".join(lines)
    msg.set_content(body)

    for item in items:
        pdf_path = Path(item["pdf_path"])
        if not pdf_path.exists():
            print(f"[첨부 실패, 건너뜀] 파일을 찾을 수 없어요: {pdf_path}")
            continue
        msg.add_attachment(
            pdf_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

    return msg


def send_alert_email(sender_address, app_password, subject, body):
    """대기함 요약이 아니라 "문제 생겼어요" 알림용 짧은 이메일 한 통을 보낸다."""
    msg = EmailMessage()
    msg["Subject"] = f"[유슬핑] {subject}"
    msg["From"] = sender_address
    msg["To"] = sender_address
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(sender_address, app_password)
        smtp.send_message(msg)


def send_email_digest(sender_address, app_password, items):
    msg = build_digest_email(sender_address, items)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(sender_address, app_password)
        smtp.send_message(msg)


def main():
    force = "--force" in sys.argv
    config = load_config()
    email_address = config["email"]["address"]
    app_password = config["email"]["app_password"]

    if not email_address or not app_password:
        print("이메일 주소나 앱 코드가 설정 안 돼있어요. 발송 설정 화면에서 먼저 입력해주세요.")
        return

    if not force and not should_send_now(config["send_time"]):
        print(f"아직 발송 시각({config['send_time']})이 안 됐거나, 오늘은 이미 발송했어요. 건너뜁니다.")
        return

    state = load_state()
    items = state.get("pending", [])

    if not items:
        print("발송 대기함이 비어있어요. 보낼 게 없어요.")
        return

    batches = batch_items_by_size(items)
    if len(batches) > 1:
        print(f"{len(items)}개 항목을 용량 때문에 {len(batches)}통으로 나눠 발송할게요...")
    else:
        print(f"{len(items)}개 항목을 이메일로 발송할게요...")

    sent_items = []
    for batch in batches:
        try:
            send_email_digest(email_address, app_password, batch)
        except smtplib.SMTPAuthenticationError:
            print("로그인 실패했어요. 앱 코드가 맞는지 발송 설정 화면에서 다시 확인해주세요.")
            break
        except Exception as e:
            print(f"발송 실패 (이 묶음은 다음에 다시 시도해요): {e}")
            break
        else:
            sent_items.extend(batch)

    if not sent_items:
        return

    print(f"발송 완료! ({len(sent_items)}/{len(items)}개)")
    sent_ids = {item["video_id"] for item in sent_items}
    state["pending"] = [item for item in items if item["video_id"] not in sent_ids]
    save_state(state)
    if not state["pending"]:
        mark_sent_today()


if __name__ == "__main__":
    main()
