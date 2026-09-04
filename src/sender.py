"""이메일 발송 담당 (Gmail 앱 비밀번호 + SMTP, OAuth 불필요).

실행: python src/sender.py (watcher.py와 같이 "따라잡기" 방식으로 반복 실행되도록 등록해서 씀)

"따라잡기" 방식: 오늘 지정한 발송 시각이 지났는데 아직 오늘 발송을 안 했으면 지금 발송한다.
컴퓨터가 그 시각에 꺼져 있었어도, 다음에 켜지면 알아서 그날치를 보낸다.
`--force`를 주면 이 판단을 건너뛰고 무조건 발송을 시도한다 (테스트/수동 실행용).

역할:
- 발송 대기함(state.yaml의 pending)에 쌓인 항목이 없으면 아무것도 하지 않는다
- 있으면 "오늘의 요약" 형태로 묶어서 PDF를 첨부한 이메일 한 통으로 발송한다
- 발송 성공 후 대기함을 비운다
"""
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from config_store import load_config
from state_store import load_state, save_state, should_send_now, mark_sent_today

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def build_digest_email(sender_address, items):
    msg = EmailMessage()
    msg["Subject"] = f"[유슬핑] 오늘의 요약 ({len(items)}개)"
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

    print(f"{len(items)}개 항목을 이메일로 발송할게요...")
    try:
        send_email_digest(email_address, app_password, items)
    except smtplib.SMTPAuthenticationError:
        print("로그인 실패했어요. 앱 코드가 맞는지 발송 설정 화면에서 다시 확인해주세요.")
        return
    except Exception as e:
        print(f"발송 실패: {e}")
        return

    print("발송 완료!")
    state["pending"] = []
    save_state(state)
    mark_sent_today()


if __name__ == "__main__":
    main()
