import uuid
import json
from datetime import date, timedelta
from database.connection import get_connection


def _calc_next_date(frequency: str, days_of_week: list[str], from_date: date) -> date:
    _DAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    if frequency == "weekly" and days_of_week:
        targets = sorted(_DAY[d] for d in days_of_week if d in _DAY)
        if not targets:
            return from_date + timedelta(weeks=1)
        dow = from_date.weekday()
        for t in targets:
            if t > dow:
                return from_date + timedelta(days=t - dow)
        return from_date + timedelta(days=7 - dow + targets[0])

    if frequency == "biweekly":
        return from_date + timedelta(weeks=2)

    if frequency == "monthly":
        m = from_date.month % 12 + 1
        y = from_date.year + (1 if from_date.month == 12 else 0)
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        max_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        return date(y, m, min(from_date.day, max_days))

    return from_date + timedelta(days=1)


def save_schedule(
    username: str,
    email: str,
    question: str,
    frequency: str,
    days_of_week: list[str],
    start_date: date,
    end_date: date | None,
) -> str:
    conn, lock = get_connection()
    sid = str(uuid.uuid4())
    next_date = _calc_next_date(frequency, days_of_week, start_date)
    with lock:
        conn.execute(
            """
            INSERT INTO scheduled_reports
                (id, username, email, question, frequency, days_of_week,
                 start_date, end_date, next_send_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [sid, username, email, question, frequency,
             json.dumps(days_of_week), start_date, end_date, next_date],
        )
    return sid


def get_due_schedules() -> list[dict]:
    conn, lock = get_connection()
    today = date.today()
    with lock:
        rows = conn.execute(
            """
            SELECT id, username, email, question, frequency,
                   days_of_week, end_date, next_send_date
            FROM scheduled_reports
            WHERE active = TRUE
              AND next_send_date <= ?
              AND (end_date IS NULL OR end_date >= ?)
            """,
            [today, today],
        ).fetchall()
    return [
        {
            "id": r[0], "username": r[1], "email": r[2], "question": r[3],
            "frequency": r[4], "days_of_week": json.loads(r[5] or "[]"),
            "end_date": r[6], "next_send_date": r[7],
        }
        for r in rows
    ]


def mark_sent(schedule_id: str, frequency: str, days_of_week: list[str], sent_date: date) -> None:
    conn, lock = get_connection()
    next_date = _calc_next_date(frequency, days_of_week, sent_date)
    with lock:
        conn.execute(
            """
            UPDATE scheduled_reports
            SET last_sent_at = CURRENT_TIMESTAMP, next_send_date = ?
            WHERE id = ?
            """,
            [next_date, schedule_id],
        )
