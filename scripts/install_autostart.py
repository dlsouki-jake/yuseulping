"""컴퓨터 시작(로그인) 시 자동 실행 등록 (macOS 전용, launchd 사용).

실행: python scripts/install_autostart.py

등록하면:
- 로그인할 때 한 번 실행됨 (RunAtLoad)
- 그 후에도 1시간마다 다시 시도됨 (StartInterval) — 실제로 확인/발송할지는
  watcher.py/sender.py가 각자 "따라잡기" 로직으로 스스로 판단함
- 실행 로그는 config/pipeline.log 에 쌓임
"""
import subprocess
import sys
from pathlib import Path

LABEL = "com.yuseulping.pipeline"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_DIR / "scripts" / "run_pipeline.sh"
LOG_PATH = PROJECT_DIR / "config" / "pipeline.log"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def main():
    if sys.platform != "darwin":
        print("지금은 macOS만 지원해요. (Windows용 작업 스케줄러 등록은 아직 준비 중이에요)")
        return

    PROJECT_DIR.joinpath("config").mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    plist_content = PLIST_TEMPLATE.format(
        label=LABEL, script_path=SCRIPT_PATH, log_path=LOG_PATH
    )
    PLIST_PATH.write_text(plist_content, encoding="utf-8")
    print(f"등록 파일 생성: {PLIST_PATH}")

    # 이미 등록돼 있으면 먼저 내리고 다시 올림 (재설치 시 안전하게)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True)

    if result.returncode != 0:
        print("등록 실패:", result.stderr)
        return

    print("자동 실행 등록 완료!")
    print("이제 로그인할 때, 그리고 이후 1시간마다 자동으로 실행 시도돼요.")
    print(f"실행 로그: {LOG_PATH}")


if __name__ == "__main__":
    main()
