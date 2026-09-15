# 유슬핑 (유튜브 슬라이드 브리핑)

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

*개인용 유튜브 요약 다이제스트 / 뉴스레터 자동화 도구*

구독 중인 유튜브 채널에 새 영상(롱폼만, 쇼츠 제외)이 올라오면 NotebookLM으로 슬라이드 요약(PDF)을
자동 생성해서, 지정한 시각에 이메일로 자동 발송해주는 개인용 무료 오픈소스 도구입니다.

> **현재 상태**: 핵심 기능(채널 등록/삭제, 신규 영상 감지, 슬라이드 생성, 이메일 발송, 자동 실행)이
> **실제 계정으로 전부 동작 확인**됐습니다. 단, **지금은 macOS 전용이에요** — Windows는 아직 테스트되지 않았고, 자동 실행 기능도 없어요. Windows 지원 기여를 환영합니다 (아래 "알려진 제약" 참고).

## 이 프로그램이 하는 일
1. 등록해둔 유튜브 채널에 새 롱폼 영상이 올라왔는지 주기적으로 확인 (컴퓨터가 켜져 있을 때마다 "밀린 만큼" 확인 — 24시간 켜둘 필요 없음)
2. 새 영상을 찾으면 NotebookLM으로 슬라이드 요약(PDF)을 자동으로 만듦
3. 만들어진 요약들을 모아서, 지정한 시각에 이메일 한 통(PDF 첨부)으로 발송

**구글 클라우드 콘솔이나 OAuth 설정이 전혀 필요 없어요.** 필요한 건 딱 두 가지뿐이에요: 채널 URL 붙여넣기, 그리고 구글 계정에서 발급받는 앱 비밀번호(코드) 하나.

## 문서
- [`PRD.md`](./PRD.md) — 무엇을 만드는지, 기능 요구사항
- [`DESIGN.md`](./DESIGN.md) — 어떻게 만들었는지, 아키텍처와 그동안의 시행착오 기록 (실제로 겪은 문제와 우회법이 자세히 적혀 있어요)

## 폴더 구조
```
config/                       사용자 설정·상태·생성된 슬라이드가 저장되는 곳
├── config.yaml                채널 목록, 이메일 설정, 발송 시각 등
├── state.yaml                 처리 이력, 발송 대기함
└── slides/                    생성된 슬라이드 PDF들

src/
├── channels.py                 채널 URL 등록/삭제 (yt-dlp)
├── recent_uploads.py           최근 업로드 조회 + 쇼츠 판별 (yt-dlp)
├── slides.py                   NotebookLM으로 슬라이드 생성
├── sender.py                   이메일 발송 (Gmail 앱 비밀번호 + SMTP)
├── watcher.py                  감지+생성 파이프라인 (실행 진입점)
├── config_store.py / state_store.py   설정·상태 읽기/쓰기
└── webui/                       로컬 웹 UI (Flask)

scripts/
├── notebooklm_login.py         NotebookLM 최초 로그인 (1회 실행)
├── run_pipeline.sh              watcher → sender 순서로 실행
└── install_autostart.py        컴퓨터 시작 시 자동 실행 등록 (macOS)
```

## 설치 방법 (macOS)

### 1. 저장소 받기
```
git clone https://github.com/dlsouki-jake/yuseulping.git
cd yuseulping
```

### 2. 실행 환경 준비
Python 3.9 이상을 권장해요.
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. NotebookLM 로그인 (최초 1회)
```
python scripts/notebooklm_login.py
```
브라우저 창이 뜨면 구글 계정으로 로그인하세요. NotebookLM 홈 화면이 보이면 자동으로 감지해서
저장하고 창이 닫혀요 (따로 엔터를 누르실 필요는 없어요).

### 4. 로컬 웹 UI 실행
```
python src/webui/app.py
```
브라우저에서 `http://localhost:5000` 접속

화면에서:
- **채널**: 요약받고 싶은 유튜브 채널 URL을 붙여넣어 등록 (최대 5개 이내 권장)
- **발송 설정**: 받을 이메일 주소 입력 + "Google에서 발급받기" 버튼으로 앱 비밀번호(코드) 발급받아 붙여넣기 + 발송 시각 선택

### 5. 컴퓨터 시작 시 자동 실행 등록 (추천)
```
python scripts/install_autostart.py
```
등록해두면 로그인할 때, 그리고 이후 1시간마다 자동으로 새 영상을 확인해요. 컴퓨터를 항상 켜둘
필요는 없고, 평소처럼 쓰기만 하면 알아서 밀린 만큼 따라잡아요.

자동 실행을 끄고 싶으면:
```
launchctl unload ~/Library/LaunchAgents/com.yuseulping.pipeline.plist
```

### (선택) 수동으로 한 번 실행해서 테스트하기
```
python src/watcher.py --force
python src/sender.py --force
```
`--force`를 붙이면 "따라잡기" 판단을 건너뛰고 바로 실행해요.

## 알아두면 좋은 점
- **Gmail 주소만 지원**해요 (다른 이메일 서비스는 안 돼요)
- **첫 슬라이드 생성은 최대 30분 가까이 걸릴 수 있어요** (실측 기준, 짧은 영상도 꽤 걸려요) — 멈춘 게 아니라 정상이에요
- NotebookLM 로그인 세션은 1~2주 정도 지나면 풀릴 수 있어요. 그럴 땐 `scripts/notebooklm_login.py`를 다시 실행하면 돼요
- 생성된 PDF는 `config/slides/`에 계속 쌓여요 (자동으로 안 지워져요)
- 이 프로그램은 여러분 컴퓨터 안에서만 실행돼요. 데이터가 외부 서버로 나가지 않아요 (구글/이메일 서버로 가는 것 제외)

## 알려진 제약
- **지금은 macOS 전용이에요.** 채널 감지·슬라이드 생성·이메일 발송 같은 핵심 로직은 파이썬으로 만들어져 있어서 원칙적으로는 Windows에서도 동작할 것으로 예상하지만, 실제로 Windows에서 테스트해본 적은 없어요. "컴퓨터 시작 시 자동 실행" 기능(`scripts/install_autostart.py`)은 macOS의 launchd 방식으로만 만들어져 있고, Windows용(작업 스케줄러)은 아직 없어요.
- **Windows 지원 기여를 환영해요!** Windows용 자동 실행 등록 스크립트나, Windows에서 직접 써보신 후 문제점 리포트를 PR/이슈로 남겨주시면 큰 도움이 돼요.
- NotebookLM/yt-dlp 모두 비공식 방식이라, 구글/유튜브가 뭔가 바꾸면 일시적으로 깨질 수 있어요
- 카카오톡 발송, 구글 드라이브 연동은 지원하지 않아요 (검토 후 1차 버전에서 제외 — 이유는 `DESIGN.md` 참고)

## 기여하기
버그 제보, 기능 제안, 코드 기여 모두 환영해요. 코드로 기여하고 싶다면:
1. 이 저장소를 **Fork**하세요 (오른쪽 위 "Fork" 버튼)
2. 새 브랜치를 만들어 작업하세요 (예: `git checkout -b fix-windows-autostart`)
3. 변경사항을 커밋하고 본인 저장소에 푸시한 뒤, **Pull Request**를 보내주세요

특히 Windows 지원(자동 실행 스크립트, 실사용 테스트)이 필요해요 — 자세한 배경은 위 "알려진 제약"을 참고해주세요.

## 라이선스
MIT License입니다. 자세한 내용은 [`LICENSE`](./LICENSE) 파일을 확인하세요.
