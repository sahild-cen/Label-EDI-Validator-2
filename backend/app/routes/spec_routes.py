from fastapi import APIRouter
from app.services.spec_engine import SpecEngine

router = APIRouter()
spec_engine = SpecEngine()


@router.post("/carriers/{carrier_name}/rollback/{version}")
async def rollback_carrier_rules(carrier_name: str, version: int):
    return await spec_engine.rollback_to_version(carrier_name, version)
