#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from SRT import SRT, SeatType
from SRT.passenger import Adult
from SRT.reservation import SRTReservation
from SRT.train import SRTTrain


DEFAULT_SECRETS_PATH = Path.home() / ".config" / "k-skill" / "secrets.env"


@dataclass
class TrainSnapshot:
    train_number: str
    dep_time: str
    arr_time: str
    general_seat_state: str | None
    special_seat_state: str | None
    seat_available: bool
    general_seat_available: bool
    special_seat_available: bool
    reserve_standby_available: bool


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hhmmss_to_hhmm(value: str) -> str:
    return f"{value[0:2]}:{value[2:4]}"


def yyyymmdd_to_kr(value: str) -> str:
    return f"{int(value[4:6])}월 {int(value[6:8])}일"


def payment_deadline_text(reservation: SRTReservation) -> str:
    if reservation.paid:
        return "이미 결제됨"
    return f"{reservation.payment_date[4:6]}월 {reservation.payment_date[6:8]}일 {reservation.payment_time[0:2]}:{reservation.payment_time[2:4]}"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        env[key] = value
    return env


class Watcher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state_dir = Path(args.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "state.json"
        self.stop_path = self.state_dir / "stop.flag"
        self.pid_path = self.state_dir / "watcher.pid"
        self.state: dict[str, Any] = read_json(self.state_path)
        self._client: Optional[SRT] = None
        self._terminated = False
        self._loop_count = int(self.state.get("loop_count", 0) or 0)

    def log(self, message: str) -> None:
        print(f"[{now_iso()}] {message}", flush=True)

    def save_state(self, **updates: Any) -> None:
        self.state.update(updates)
        self.state["updated_at"] = now_iso()
        self.state["config"] = {
            "dep": self.args.dep,
            "arr": self.args.arr,
            "date": self.args.date,
            "start_time": self.args.start_time,
            "end_time": self.args.end_time,
            "target_train_number": self.args.target_train_number,
            "target_dep_time": self.args.target_dep_time,
            "mode": self.args.mode,
            "poll_seconds": self.args.poll_seconds,
            "seat_preference": self.args.seat_preference,
            "notify": self.args.notify,
            "telegram_chat_id": self.args.telegram_chat_id,
            "secrets_path": str(self.args.secrets_path),
        }
        atomic_write_json(self.state_path, self.state)

    def handle_signal(self, signum: int, _frame: Any) -> None:
        self._terminated = True
        self.save_state(status="stopped", stop_reason=f"signal:{signum}")

    def should_stop(self) -> bool:
        return self._terminated or self.stop_path.exists()

    def load_credentials(self) -> None:
        env_from_file = parse_env_file(self.args.secrets_path)
        for key, value in env_from_file.items():
            os.environ.setdefault(key, value)

        missing = [key for key in ("KSKILL_SRT_ID", "KSKILL_SRT_PASSWORD") if not os.environ.get(key)]
        if missing:
            raise RuntimeError(f"missing SRT credentials: {', '.join(missing)}")

    def get_client(self) -> SRT:
        if self._client is None:
            self.load_credentials()
            self._client = SRT(os.environ["KSKILL_SRT_ID"], os.environ["KSKILL_SRT_PASSWORD"])
        return self._client

    def reset_client(self) -> None:
        self._client = None

    def seat_preference(self) -> SeatType:
        return {
            "general-first": SeatType.GENERAL_FIRST,
            "general-only": SeatType.GENERAL_ONLY,
            "special-first": SeatType.SPECIAL_FIRST,
            "special-only": SeatType.SPECIAL_ONLY,
        }[self.args.seat_preference]

    def match_reservation(self, reservation: SRTReservation) -> bool:
        if reservation.dep_date != self.args.date:
            return False
        if reservation.dep_station_name != self.args.dep or reservation.arr_station_name != self.args.arr:
            return False
        if not (self.args.start_time <= reservation.dep_time <= self.args.end_time):
            return False
        if self.args.target_train_number and reservation.train_number != self.args.target_train_number:
            return False
        if self.args.target_dep_time and reservation.dep_time != self.args.target_dep_time:
            return False
        return True

    def match_train(self, train: SRTTrain) -> bool:
        if not (self.args.start_time <= train.dep_time <= self.args.end_time):
            return False
        if self.args.target_train_number and train.train_number != self.args.target_train_number:
            return False
        if self.args.target_dep_time and train.dep_time != self.args.target_dep_time:
            return False
        return True

    def list_matching_reservations(self, client: SRT) -> list[SRTReservation]:
        reservations = client.get_reservations(paid_only=False)
        matched = [reservation for reservation in reservations if self.match_reservation(reservation)]
        matched.sort(key=lambda item: (item.dep_time, item.train_number, item.reservation_number))
        return matched

    def reservations_payload(self, reservations: list[SRTReservation]) -> list[dict[str, Any]]:
        return [
            {
                "reservation_number": r.reservation_number,
                "train_number": r.train_number,
                "dep_date": r.dep_date,
                "dep_time": r.dep_time,
                "arr_time": r.arr_time,
                "dep_station_name": r.dep_station_name,
                "arr_station_name": r.arr_station_name,
                "payment_date": r.payment_date,
                "payment_time": r.payment_time,
                "paid": r.paid,
                "total_cost": r.total_cost,
                "seat_count": r.seat_count,
            }
            for r in reservations
        ]

    def train_snapshots(self, trains: list[SRTTrain]) -> list[dict[str, Any]]:
        return [
            asdict(
                TrainSnapshot(
                    train_number=train.train_number,
                    dep_time=train.dep_time,
                    arr_time=train.arr_time,
                    general_seat_state=getattr(train, "general_seat_state", None),
                    special_seat_state=getattr(train, "special_seat_state", None),
                    seat_available=train.seat_available(),
                    general_seat_available=train.general_seat_available(),
                    special_seat_available=train.special_seat_available(),
                    reserve_standby_available=train.reserve_standby_available(),
                )
            )
            for train in trains
        ]

    def fetch_window_trains(self, client: SRT) -> tuple[list[SRTTrain], list[dict[str, Any]]]:
        trains = client.search_train(
            self.args.dep,
            self.args.arr,
            self.args.date,
            self.args.start_time,
            time_limit=self.args.end_time,
            available_only=False,
        )
        matched = [train for train in trains if self.match_train(train)]
        matched.sort(key=lambda item: (item.dep_time, int(item.train_number)))
        return matched, self.train_snapshots(matched)

    def train_bookable_for_preference(self, train: SRTTrain) -> bool:
        if self.args.seat_preference == "general-only":
            return train.general_seat_available()
        if self.args.seat_preference == "special-only":
            return train.special_seat_available()
        return train.seat_available()

    def choose_bookable_train(self, trains: list[SRTTrain]) -> Optional[SRTTrain]:
        for train in trains:
            if self.train_bookable_for_preference(train):
                return train
        return None

    def send_telegram(self, text: str) -> tuple[bool, str]:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = self.args.telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return False, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
        if resp.ok:
            return True, resp.text[:500]
        return False, f"HTTP {resp.status_code}: {resp.text[:500]}"

    def notify(self, text: str) -> tuple[bool, str]:
        if self.args.notify == "stdout":
            self.log(f"NOTIFY: {text}")
            return True, "stdout"
        if self.args.notify == "telegram":
            return self.send_telegram(text)
        return False, f"unknown notify mode: {self.args.notify}"

    def notify_booking(self, reservation: SRTReservation, continuous: bool = False, reserved_total: int | None = None) -> None:
        if continuous:
            message = (
                f"SRT 자동예약 성공: {yyyymmdd_to_kr(reservation.dep_date)} {reservation.dep_station_name}→{reservation.arr_station_name} "
                f"{hhmmss_to_hhmm(reservation.dep_time)} 출발 {reservation.train_number}열차 1석 예약 완료. "
                f"현재 누적 예약 좌석 {reserved_total}석. 구입기한 {payment_deadline_text(reservation)}"
            )
        else:
            message = (
                f"SRT 자동예약 완료: {yyyymmdd_to_kr(reservation.dep_date)} {reservation.dep_station_name}→{reservation.arr_station_name} "
                f"{hhmmss_to_hhmm(reservation.dep_time)} 출발 {reservation.train_number}열차 예약 완료. "
                f"요금 {reservation.total_cost}원, 구입기한 {payment_deadline_text(reservation)}"
            )
        ok, detail = self.notify(message)
        self.save_state(
            last_notification_at=now_iso(),
            last_notification_ok=ok,
            last_notification_detail=detail,
            last_notification_message=message,
        )
        if not ok:
            raise RuntimeError(f"notification failed: {detail}")

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        self.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        self.save_state(status="starting", started_at=self.state.get("started_at") or now_iso())
        self.log(
            f"watcher started for {self.args.date} {self.args.dep}->{self.args.arr} {self.args.start_time}-{self.args.end_time}, "
            f"poll={self.args.poll_seconds}s, mode={self.args.mode}"
        )

        while not self.should_stop():
            self._loop_count += 1
            try:
                client = self.get_client()
                existing = self.list_matching_reservations(client)
                reserved_total = sum(int(getattr(r, "seat_count", 0) or 0) for r in existing)
                self.save_state(
                    status="watching",
                    loop_count=self._loop_count,
                    last_checked_at=now_iso(),
                    matching_reservations=self.reservations_payload(existing),
                    reserved_seat_total=reserved_total,
                    last_error=None,
                )

                trains, snapshots = self.fetch_window_trains(client)
                self.save_state(
                    last_snapshot=snapshots,
                    last_snapshot_at=now_iso(),
                    train_count=len(trains),
                )

                if self.args.mode == "target-total" and existing:
                    self.log(f"matching reservation already exists: {existing[0].reservation_number}")
                    self.save_state(status="done", stop_reason="existing_reservation")
                    return 0

                target_train = self.choose_bookable_train(trains)
                if target_train is not None:
                    self.log(
                        f"seat detected on train {target_train.train_number} at {hhmmss_to_hhmm(target_train.dep_time)}; attempting reserve"
                    )
                    reservation = client.reserve(
                        target_train,
                        passengers=[Adult(1)],
                        special_seat=self.seat_preference(),
                    )
                    self.log(f"reservation succeeded: {reservation.reservation_number}")

                    if self.args.mode == "continuous-single":
                        existing = self.list_matching_reservations(client)
                        reserved_total = sum(int(getattr(r, 'seat_count', 0) or 0) for r in existing)
                        self.notify_booking(reservation, continuous=True, reserved_total=reserved_total)
                        continue

                    self.notify_booking(reservation, continuous=False)
                    self.save_state(status="done", stop_reason="reserved_and_notified")
                    return 0

                time.sleep(self.args.poll_seconds)
            except Exception as exc:
                detail = "".join(traceback.format_exception(exc)).strip()
                self.reset_client()
                self.log(detail)
                self.save_state(
                    status="error_retrying",
                    last_error=str(exc),
                    last_error_detail=detail,
                    last_error_at=now_iso(),
                )
                if self.should_stop():
                    break
                time.sleep(min(max(self.args.poll_seconds, 15), 60))

        self.save_state(status="stopped", stop_reason="stop_requested")
        self.log("watcher stopped")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Background SRT auto-book watcher")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--dep", required=True)
    parser.add_argument("--arr", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--target-train-number")
    parser.add_argument("--target-dep-time")
    parser.add_argument("--mode", choices=["target-total", "continuous-single"], default="target-total")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--notify", choices=["stdout", "telegram"], default="stdout")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument(
        "--seat-preference",
        default="general-first",
        choices=["general-first", "general-only", "special-first", "special-only"],
    )
    parser.add_argument("--secrets-path", type=Path, default=DEFAULT_SECRETS_PATH)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    watcher = Watcher(args)
    return watcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
