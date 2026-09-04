#!/bin/bash
# 감지+생성(watcher) → 발송(sender) 순서로 한 번 실행하는 스크립트.
# 자동 실행 등록(scripts/install_autostart.py)이 이 스크립트를 반복 호출한다.
# 둘 다 내부적으로 "따라잡기" 판단을 하기 때문에, 이 스크립트는 자주 호출돼도 안전하다.

set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

python src/watcher.py
python src/sender.py
