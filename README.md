# SRT / KTX Auto Booking

민감정보 없이 그대로 공유할 수 있도록 정리한, GitHub 공개용 SRT / KTX 자동 예약 도구 모음입니다.

이 패키지는 다음 목적에 맞춰 구성했습니다.
- 다른 사람이 GitHub 에서 clone 해서 바로 실행할 수 있게 만들기
- 계정정보 / 토큰 / 개인 state 파일은 저장소 밖에 두기
- KTX 는 CLI helper, SRT 는 자동감시 watcher 형태로 재사용하기

중요한 제한사항
- 결제 자동화는 포함하지 않습니다.
- 실시간 예약 성공을 보장하지 않습니다.
- 철도사 사이트 정책 변경, 로그인 차단, CAPTCHA, API 변경 등에 따라 언제든 동작이 달라질 수 있습니다.
- 본인 계정으로만 사용하세요.

## 포함 파일

- `scripts/ktx_booking.py`
  - KTX 조회 / 예약 / 예약조회 / 취소 CLI
- `scripts/srt_autobook_watcher.py`
  - SRT 자동감시 / 자동예약 watcher
- `.env.example`
  - 자격정보 예시 파일
- `requirements.txt`
  - 필요한 Python 패키지
- `examples/srt_watch_example.sh`
  - SRT 자동감시 실행 예시
- `examples/ktx_search_example.sh`
  - KTX 조회 실행 예시
- `examples/ktx_reservations_example.sh`
  - KTX 예약조회 실행 예시

## 저장소에 포함하면 안 되는 것

절대 커밋하지 마세요.
- 실제 계정 ID / 비밀번호
- 실제 `.env`
- 텔레그램 봇 토큰
- state 디렉터리 안의 런타임 상태 파일
- 개인 로그 파일

`.gitignore` 에 기본적으로 아래 항목이 포함되어 있습니다.
- `.env`
- `state/`
- `__pycache__/`
- `*.pyc`

## 빠른 시작

### 1) clone

```bash
git clone <YOUR_REPO_URL>
cd train-booking-share
```

### 2) 가상환경 생성

Linux / macOS / WSL:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3) 환경변수 파일 만들기

```bash
cp .env.example .env
```

그 다음 `.env` 를 열어서 본인 값으로 수정하세요.

필수 값
- `KSKILL_SRT_ID`
- `KSKILL_SRT_PASSWORD`
- `KSKILL_KTX_ID`
- `KSKILL_KTX_PASSWORD`

선택 값
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 4) 환경변수 로드

bash / zsh:

```bash
set -a
. ./.env
set +a
```

PowerShell:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^(\s*#|\s*$)') { return }
  $name, $value = $_ -split '=', 2
  [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), 'Process')
}
```

## KTX 사용법

### KTX 조회

```bash
python3 scripts/ktx_booking.py search 서울 부산 20260328 090000 --limit 5
```

좌석 없는 열차 / 대기 포함 조회:

```bash
python3 scripts/ktx_booking.py search 서울 부산 20260328 090000 --limit 10 --include-no-seats --include-waiting-list
```

예시 스크립트:

```bash
bash examples/ktx_search_example.sh
```

### KTX 예약

먼저 `search` 결과에서 `train_id` 를 얻은 뒤 예약합니다.

```bash
python3 scripts/ktx_booking.py reserve 서울 부산 20260328 090000 --train-id <train_id> --seat-option general-first
```

2인 예약 예시:

```bash
python3 scripts/ktx_booking.py reserve 서울 부산 20260328 090000 --train-id <train_id> --adults 2 --seat-option general-only
```

### KTX 예약조회

```bash
python3 scripts/ktx_booking.py reservations
```

예시 스크립트:

```bash
bash examples/ktx_reservations_example.sh
```

### KTX 취소

```bash
python3 scripts/ktx_booking.py cancel <reservation_id>
```

## SRT 사용법

### SRT watcher 개념

`scripts/srt_autobook_watcher.py` 는 아래 방식으로 동작합니다.
- `available_only=False` 로 열차를 조회합니다.
- 지정 시간대만 `dep_time` 으로 다시 필터링합니다.
- 일반실 / 특실 중 하나라도 예약 가능하면 예약을 시도합니다.
- `target-total` 모드: 조건에 맞는 예약 1건이 생기면 종료합니다.
- `continuous-single` 모드: 1석씩 계속 시도하며 stop 요청 전까지 반복합니다.

### SRT 자동감시 / 자동예약 실행 예시

```bash
python3 scripts/srt_autobook_watcher.py \
  --state-dir ./state/srt-suseo-daejeon-20260508 \
  --dep 수서 \
  --arr 대전 \
  --date 20260508 \
  --start-time 200000 \
  --end-time 205959 \
  --mode target-total \
  --poll-seconds 20 \
  --seat-preference general-first \
  --notify stdout
```

예시 스크립트:

```bash
bash examples/srt_watch_example.sh
```

### 특정 열차만 감시

```bash
python3 scripts/srt_autobook_watcher.py \
  --state-dir ./state/srt-train369 \
  --dep 수서 \
  --arr 대전 \
  --date 20260508 \
  --start-time 200000 \
  --end-time 205959 \
  --target-train-number 369 \
  --mode continuous-single \
  --poll-seconds 20 \
  --seat-preference general-first \
  --notify stdout
```

### Telegram 알림 사용

`.env` 안에 `TELEGRAM_BOT_TOKEN` 이 있어야 합니다.

```bash
python3 scripts/srt_autobook_watcher.py \
  --state-dir ./state/srt-suseo-daejeon-20260508 \
  --dep 수서 \
  --arr 대전 \
  --date 20260508 \
  --start-time 200000 \
  --end-time 205959 \
  --mode target-total \
  --poll-seconds 20 \
  --seat-preference general-first \
  --notify telegram \
  --telegram-chat-id <CHAT_ID>
```

### 중지 방법

아래 파일을 만들면 watcher 가 다음 루프에서 종료됩니다.

```bash
touch ./state/srt-suseo-daejeon-20260508/stop.flag
```

### 상태 확인

watcher 는 `state.json` 을 계속 갱신합니다.

주요 필드 예시
- `status`
- `last_checked_at`
- `matching_reservations`
- `reserved_seat_total`
- `last_snapshot`
- `last_error`
- `last_notification_at`

## 자주 하는 실수

### 1) .env 를 안 불러온 경우
증상:
- 로그인 실패
- 필수 환경변수 없음

확인:
- 현재 셸에서 `.env` 를 다시 로드했는지 확인
- 오타 없이 변수명이 맞는지 확인

### 2) train_id 를 오래된 값으로 사용한 경우
증상:
- KTX reserve 에서 stale / invalid train_id 류 오류

해결:
- 항상 새로 `search` 를 한 뒤 그 결과의 `train_id` 를 다시 사용

### 3) SRT 감시를 중복으로 돌린 경우
증상:
- 같은 열차를 여러 프로세스가 동시에 잡으려 함
- 중복 알림 / 중복 예약 시도 위험

해결:
- 같은 조건의 watcher 는 하나만 유지
- `state-dir` 을 구분
- systemd / cron / 다른 에이전트와 중복 실행 중인지 확인

### 4) Telegram 알림이 안 오는 경우
확인:
- `.env` 에 `TELEGRAM_BOT_TOKEN` 존재 여부
- `--telegram-chat-id` 값 확인
- 봇이 해당 chat 에 메시지를 보낼 권한이 있는지 확인

## 운영 팁

- 공개 저장소에는 절대 `.env` 를 넣지 마세요.
- 처음엔 `--notify stdout` 으로 로컬 테스트부터 하세요.
- 실제 감시는 짧은 시간 / 테스트 계정 / 작은 범위로 먼저 검증하세요.
- 자동예약은 부작용이 있으므로 동일 시간대의 다른 watcher 와 중복 실행하지 않는 편이 안전합니다.

## GitHub 업로드 예시

```bash
git init
git add .
git commit -m "Initial shareable KTX/SRT booking package"
git branch -m main
git remote add origin <YOUR_REPO_URL>
git push -u origin main
```

## 마지막 체크리스트

업로드 전에 아래만 다시 확인하세요.
- `.env` 가 없는지
- `state/` 안 파일이 비어 있거나 제외되는지
- README 예시에 개인 경로 / 개인 ID / 개인 토큰이 없는지
- 테스트 로그에 민감정보가 남아 있지 않은지
