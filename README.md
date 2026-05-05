# SRT / KTX Auto Booking

K-Skill 기반 자산을 바탕으로 정리한 SRT / KTX 예약 도구 모음입니다.
- KTX: 조회, 예약, 예약조회, 취소 CLI
- SRT: 자동감시 및 자동예약 watcher

## 포함 파일
- `scripts/ktx_booking.py` : KTX CLI
- `scripts/srt_autobook_watcher.py` : SRT watcher
- `.env.example` : 환경변수 예시
- `examples/` : 실행 예시 스크립트

## 빠른 시작

### 1. 설치
```bash
git clone <YOUR_REPO_URL>
cd srt-ktx-auto-booking
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

### 2. 환경변수 설정
```bash
cp .env.example .env
```

필수:
- `KSKILL_SRT_ID`
- `KSKILL_SRT_PASSWORD`
- `KSKILL_KTX_ID`
- `KSKILL_KTX_PASSWORD`

선택:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

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

### 조회
```bash
python3 scripts/ktx_booking.py search 서울 부산 20260328 090000 --limit 5
```

좌석 없음 / 대기 포함:
```bash
python3 scripts/ktx_booking.py search 서울 부산 20260328 090000 --limit 10 --include-no-seats --include-waiting-list
```

### 예약
먼저 `search` 결과의 `train_id` 를 확인한 뒤 예약합니다.
```bash
python3 scripts/ktx_booking.py reserve 서울 부산 20260328 090000 --train-id <train_id> --seat-option general-first
```

2인 예약 예시:
```bash
python3 scripts/ktx_booking.py reserve 서울 부산 20260328 090000 --train-id <train_id> --adults 2 --seat-option general-only
```

### 예약조회
```bash
python3 scripts/ktx_booking.py reservations
```

### 취소
```bash
python3 scripts/ktx_booking.py cancel <reservation_id>
```

예시:
```bash
bash examples/ktx_search_example.sh
bash examples/ktx_reservations_example.sh
```

## SRT 사용법

### 기본 실행
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

### Telegram 알림
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

예시:
```bash
bash examples/srt_watch_example.sh
```

### 중지
```bash
touch ./state/srt-suseo-daejeon-20260508/stop.flag
```

### 상태 파일
watcher 는 `state.json` 을 갱신합니다.
주요 필드:
- `status`
- `last_checked_at`
- `matching_reservations`
- `reserved_seat_total`
- `last_snapshot`
- `last_error`
- `last_notification_at`

## 주의사항
- 결제 자동화는 포함하지 않습니다.
- 실시간 예약 성공을 보장하지 않습니다.
- `.env`, `state/`, 로그 파일은 저장소에 포함하지 마세요.
- KTX 예약은 항상 최신 `search` 결과의 `train_id` 를 사용하세요.
- 같은 조건의 SRT watcher 를 여러 개 동시에 실행하지 마세요.
