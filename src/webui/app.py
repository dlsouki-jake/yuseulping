"""설정 화면(로컬 웹 UI) — Flask 서버.

실행: python src/webui/app.py
브라우저에서 http://localhost:5000 접속
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # src/ 폴더를 import 경로에 추가

from flask import Flask, flash, redirect, render_template, request, url_for

import channels as channels_module
from config_store import load_config, save_config
from state_store import load_state
from datetime import date

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

SEND_TIME_OPTIONS = [f"{h:02d}:00" for h in range(6, 19)]  # 06:00 ~ 18:00


def create_app():
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
    app.secret_key = "local-only-dev-secret"  # 외부에 노출되지 않는 로컬 전용 서버라 고정값 사용

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
    app.run(host="0.0.0.0", port=5000, debug=True)
