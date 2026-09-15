"""설정 화면(로컬 웹 UI) — Flask 서버.

실행: python src/webui/app.py
브라우저에서 http://localhost:5000 접속
"""
import secrets
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # src/ 폴더를 import 경로에 추가

from flask import Flask, flash, redirect, render_template, request, session, url_for

import channels as channels_module
from config_store import CONFIG_DIR, load_config, save_config
from state_store import load_state
from datetime import date

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TOKEN_PATH = CONFIG_DIR / "webui.token"  # .gitignore의 config/*.token 패턴으로 항상 제외됨

SEND_TIME_OPTIONS = [f"{h:02d}:00" for h in range(6, 19)]  # 06:00 ~ 18:00


def get_or_create_access_token():
    """이 웹 UI 접속용 토큰을 읽거나, 없으면 새로 만들어 저장한다.

    host="0.0.0.0"이라 같은 네트워크의 다른 기기(폰 등)에서도 접속 가능하게
    설계돼 있는데, 그렇다고 아무나 들어올 수 있으면 안 되니 무작위 토큰을
    URL에 넣도록 해서 이 토큰을 아는 사람(=이 컴퓨터를 쓰는 본인)만 접속할
    수 있게 한다. Jupyter Notebook의 접속 토큰과 같은 방식.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(16)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


def create_app():
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
    access_token = get_or_create_access_token()
    app.secret_key = access_token  # 세션 서명에도 같은 토큰을 재사용 (별도 관리 불필요)

    @app.before_request
    def require_access_token():
        if request.endpoint == "static":
            return  # CSS 등 정적 파일은 그대로 허용
        if session.get("authorized"):
            return
        supplied = request.args.get("token", "")
        if supplied and secrets.compare_digest(supplied, access_token):
            session["authorized"] = True
            session.permanent = True
            return redirect(request.path)  # 주소창에서 토큰을 지운 깨끗한 URL로 이동
        return (
            "접속하려면 서버를 실행한 터미널에 표시된, 토큰이 포함된 주소로 들어와야 해요.",
            403,
        )

    @app.route("/")
    def home():
        return render_template("home.html", active="home")

    @app.route("/channels", methods=["GET", "POST"])
    def channels():
        if request.method == "POST":
            url = request.form.get("url", "").strip()
            if url:
                try:
                    channels_module.add_channel(url)
                    flash("채널을 등록했어요.", "good")
                except Exception:
                    flash("채널 정보를 가져오지 못했어요. URL을 다시 확인해주세요.", "error")
            return redirect(url_for("channels"))

        config = load_config()
        return render_template(
            "channels.html",
            active="channels",
            channels=config["channels"],
            recommended_limit=config["recommended_channel_limit"],
        )

    @app.route("/channels/<channel_id>/delete", methods=["POST"])
    def delete_channel(channel_id):
        channels_module.remove_channel(channel_id)
        flash("채널을 삭제했어요.", "good")
        return redirect(url_for("channels"))

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        config = load_config()

        if request.method == "POST":
            config["email"]["address"] = request.form.get("email_address", "").strip()
            new_password = request.form.get("app_password", "").strip()
            if new_password:
                config["email"]["app_password"] = new_password
            config["send_time"] = request.form.get("send_time", config["send_time"])
            save_config(config)
            flash("저장했어요.", "good")
            return redirect(url_for("settings"))

        return render_template(
            "settings.html",
            active="settings",
            email_address=config["email"]["address"],
            has_app_password=bool(config["email"]["app_password"]),
            send_time=config["send_time"],
            send_time_options=SEND_TIME_OPTIONS,
        )

    @app.route("/dashboard")
    def dashboard():
        config = load_config()
        state = load_state()

        today = date.today().isoformat()
        generated_today = state.get("generated_count", 0) if state.get("generated_date") == today else 0

        activity = []
        for item in state.get("pending", []):
            activity.append({"title": item["title"], "channel": item["channel_title"], "status": "완료 · 발송 대기", "kind": "good"})
        for item in state.get("queued", []):
            reason = "재시도 예정" if item.get("retry_count", 0) > 0 else "대기 중"
            activity.append({"title": item["title"], "channel": item["channel_title"], "status": reason, "kind": "warn"})
        for item in state.get("failed", []):
            activity.append({"title": item["title"], "channel": item["channel_title"], "status": f"실패 · {item.get('reason', '')[:40]}", "kind": "critical"})

        return render_template(
            "dashboard.html",
            active="dashboard",
            channel_count=len(config["channels"]),
            send_time=config["send_time"],
            pending_count=len(state.get("pending", [])),
            generated_today=generated_today,
            login_needed=state.get("login_needed", False),
            activity=activity,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    token = get_or_create_access_token()
    print("\n브라우저에서 아래 주소로 접속하세요 (토큰이 포함돼 있어야 접속이 허용돼요):")
    print(f"  http://localhost:5000/?token={token}")
    print("같은 와이파이의 폰 등 다른 기기에서 접속하려면 'localhost' 대신 이 컴퓨터의")
    print("IP 주소를 쓰고, 뒤에 '?token=...'을 똑같이 붙이면 돼요.\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
