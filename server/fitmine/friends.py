"""Friends: follow each other's training and compare.

  friend_codes   a short random code per user, to share instead of an email
  friendships    requester -> addressee, 'pending' until the addressee accepts

Friends see each other's name, streak, weekly totals, fitness level, training style and
sets per muscle. Never single workouts, times of day or GPS tracks.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from . import live
from . import training as TR
from .data import store

DDL = [
    "CREATE TABLE IF NOT EXISTS friend_codes (user_id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL)",
    "CREATE TABLE IF NOT EXISTS friendships (requester INTEGER NOT NULL, addressee INTEGER NOT NULL, "
    "status TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (requester, addressee))",
]
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I


class FriendError(ValueError):
    pass


def ensure_tables(con):
    with store._lock:
        for sql in DDL:
            con.execute(sql)
        con.commit()


def code(con, user_id: int) -> str:
    r = con.execute("SELECT code FROM friend_codes WHERE user_id=?", (int(user_id),)).fetchone()
    if r:
        return r[0]
    with store._lock:
        while True:
            c = "".join(secrets.choice(ALPHABET) for _ in range(8))
            if not con.execute("SELECT 1 FROM friend_codes WHERE code=?", (c,)).fetchone():
                break
        con.execute("INSERT INTO friend_codes (user_id, code) VALUES (?,?)", (int(user_id), c))
        con.commit()
    return c


def find(con, handle: str) -> int | None:
    """A friend's email address or friend code -> their user id."""
    h = handle.strip()
    if "@" in h:
        r = con.execute("SELECT user_id FROM accounts WHERE email=?", (h.lower(),)).fetchone()
    else:
        r = con.execute("SELECT user_id FROM friend_codes WHERE code=?",
                        ("".join(ch for ch in h.upper() if ch.isalnum()),)).fetchone()
    return None if r is None else int(r[0])


def _link(con, a: int, b: int):
    return con.execute("SELECT requester, addressee, status FROM friendships WHERE (requester=? AND addressee=?) "
                       "OR (requester=? AND addressee=?)", (a, b, b, a)).fetchone()


def are_friends(con, a: int, b: int) -> bool:
    r = _link(con, int(a), int(b))
    return r is not None and r[2] == "accepted"


def request(con, user_id: int, handle: str) -> str:
    """Send a request; if they already asked us, this accepts it. Returns 'pending' or 'accepted'."""
    other = find(con, handle)
    if other is None:
        raise FriendError("No FitMine account has that email or friend code.")
    if other == user_id:
        raise FriendError("That's you. Share your code with a friend instead.")
    r = _link(con, user_id, other)
    if r is not None:
        if r[2] == "accepted":
            raise FriendError("You're already friends.")
        if r[0] == user_id:
            raise FriendError("You've already sent them a request.")
        accept(con, user_id, other)
        return "accepted"
    con.execute("INSERT INTO friendships (requester, addressee, status, created_at) VALUES (?,?,?,?)",
                (int(user_id), int(other), "pending", datetime.now().strftime(live.TS)))
    con.commit()
    return "pending"


def accept(con, user_id: int, other: int) -> bool:
    hit = con.execute("SELECT 1 FROM friendships WHERE requester=? AND addressee=? AND status='pending'",
                      (int(other), int(user_id))).fetchone()
    if not hit:
        return False
    con.execute("UPDATE friendships SET status='accepted' WHERE requester=? AND addressee=?", (int(other), int(user_id)))
    con.commit()
    return True


def remove(con, user_id: int, other: int) -> bool:
    """Unfriend, decline a request, or cancel one we sent."""
    if _link(con, int(user_id), int(other)) is None:
        return False
    con.execute("DELETE FROM friendships WHERE (requester=? AND addressee=?) OR (requester=? AND addressee=?)",
                (int(user_id), int(other), int(other), int(user_id)))
    con.commit()
    return True


def _name(con, user_id: int) -> str:
    r = con.execute("SELECT name FROM live_users WHERE user_id=?", (int(user_id),)).fetchone()
    return r[0] if r else "?"


def summary(con, user_id: int, today: date) -> dict:
    """The few numbers shown in the friends list and leaderboard."""
    s = TR.streak(con, user_id, today)
    start = TR.monday(today)
    four = (start - timedelta(weeks=3)).isoformat()
    w = live.workouts(con, user_id, "AND NOT flagged AND start_time >= ?", (four,))
    w = w[w.start_time.str[:10] <= today.isoformat()]
    wk = w[w.start_time >= start.isoformat()]
    return {"user_id": int(user_id), "name": _name(con, user_id), "streak": s["current"], "longest_streak": s["longest"],
            "today_done": s["today_done"], "week_sessions": int(len(wk)), "week_minutes": float(wk.duration_min.sum()),
            "four_week_minutes": float(w.duration_min.sum()),
            "last_workout": None if w.empty else str(w.start_time.max())[:10]}


def listing(con, user_id: int, today: date) -> dict:
    rows = con.execute("SELECT requester, addressee, status, created_at FROM friendships WHERE requester=? OR addressee=?",
                       (int(user_id), int(user_id))).fetchall()
    friends, incoming, outgoing = [], [], []
    for req, addr, status, created in rows:
        other = addr if req == user_id else req
        if status == "accepted":
            friends.append(summary(con, other, today))
        else:
            (outgoing if req == user_id else incoming).append(
                {"user_id": int(other), "name": _name(con, other), "since": created[:10]})
    me = summary(con, user_id, today)
    board = sorted([me, *friends], key=lambda x: (-x["week_minutes"], -x["streak"]))
    return {"code": code(con, user_id), "me": me, "friends": sorted(friends, key=lambda x: x["name"].lower()),
            "incoming": incoming, "outgoing": outgoing, "leaderboard": [x["user_id"] for x in board]}


def snapshot(con, user_id: int, today: date) -> dict:
    """What a friend may see, side by side with the user's own."""
    p = live.profile(con, user_id)
    s = summary(con, user_id, today)
    start = TR.monday(today) - timedelta(weeks=7)
    w = live.workouts(con, user_id, "AND NOT flagged AND start_time >= ?", (start.isoformat(),))
    w = w[w.start_time.str[:10] <= today.isoformat()]
    weeks = [(start + timedelta(weeks=i)).isoformat() for i in range(8)]
    wk = [TR.monday(date.fromisoformat(d[:10])).isoformat() for d in w.start_time]
    by = w.assign(week=wk).groupby("week").agg(minutes=("duration_min", "sum"), sessions=("workout_id", "size"))
    return {
        **s, "level": p["level"]["value"], "persona": p["persona"]["name"],
        "stats": {k: p["stats"].get(k) for k in ("sessions_per_week", "minutes_per_week", "run_pace", "longest_km",
                                                 "vo2max")},
        "weekly": [{"week": k, "minutes": float(by.minutes.get(k, 0.0)), "sessions": int(by.sessions.get(k, 0))}
                   for k in weeks],
        "muscle_sets": TR.muscle_sets_per_week(con, user_id, today),
    }
