"""Friends: requests by email or friend code, the leaderboard, and side-by-side comparison.
A friend's numbers are only readable once both sides have accepted."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from fitmine import friends as F
from fitmine import training as TR
from fitmine.analyses.common import jsonable

from ..schemas import Comparison, FriendRequestIn, FriendRequestResult, Friends
from .account import current_user, db

router = APIRouter(prefix="/api/me/friends", tags=["account"])


@router.get("", response_model=Friends)
def friends(today: str | None = None, uid: int = Depends(current_user), con=Depends(db)):
    return F.listing(con, uid, TR.parse_today(today))


@router.post("", response_model=FriendRequestResult)
def add(req: FriendRequestIn, uid: int = Depends(current_user), con=Depends(db)):
    try:
        return {"status": F.request(con, uid, req.handle)}
    except F.FriendError as e:
        raise HTTPException(400, str(e))


@router.post("/{friend_id}/accept", status_code=204)
def accept(friend_id: int, uid: int = Depends(current_user), con=Depends(db)):
    if not F.accept(con, uid, friend_id):
        raise HTTPException(404, "No request from them to accept.")
    return Response(status_code=204)


@router.delete("/{friend_id}", status_code=204)
def remove(friend_id: int, uid: int = Depends(current_user), con=Depends(db)):
    if not F.remove(con, uid, friend_id):
        raise HTTPException(404, "They aren't on your friends list.")
    return Response(status_code=204)


@router.get("/{friend_id}/compare", response_model=Comparison)
def compare(friend_id: int, today: str | None = None, uid: int = Depends(current_user), con=Depends(db)):
    if not F.are_friends(con, uid, friend_id):
        raise HTTPException(404, "They aren't on your friends list.")
    d = TR.parse_today(today)
    return jsonable({"me": F.snapshot(con, uid, d), "friend": F.snapshot(con, friend_id, d)})
