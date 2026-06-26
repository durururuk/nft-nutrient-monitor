from fastapi import APIRouter

import database
from models import TargetSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/target", response_model=TargetSettings)
async def get_target():
    """현재 목표값(EC/pH) 조회."""
    return await database.get_target()


@router.post("/target", response_model=TargetSettings)
async def set_target(req: TargetSettings):
    """목표값(EC/pH) 저장 후 저장된 값 반환."""
    return await database.set_target(ec=req.ec, ph=req.ph)
