"""S3-004 受控修复提案 API（只生成提案、绝不执行设备配置，NEXT/S3 后端切片）。

- POST   /api/sdn/vpcs/{vpc_id}/remediation-proposals           创建（准入+防陈旧，幂等）
- GET    /api/sdn/vpcs/{vpc_id}/remediation-proposals           列表（读取时保守标 stale）
- GET    /api/sdn/vpcs/{vpc_id}/remediation-proposals/{id}      详情（读取时保守标 stale）
- POST   /api/sdn/vpcs/{vpc_id}/remediation-proposals/{id}/cancel  取消（仅 proposed，幂等）

服务端从 run 白名单 items 取 device/item，不信任调用方重填设备或动作；action 固定
redeploy_vpc_on_device。全路径零设备 I/O；不实现 confirm/apply，不把 proposed 写成已修复。
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n_keys import err, error_response
from app.schemas import APIResponse
from app.services import sdn_remediation as remed
from app.services.sdn_remediation import (
    ProposalRejected,
    serialize_proposal,
)

router = APIRouter(prefix="/api/sdn", tags=["sdn-remediation"])


@router.post("/vpcs/{vpc_id}/remediation-proposals", response_model=APIResponse)
def create_remediation_proposal(vpc_id: int, body: dict, db: Session = Depends(get_db)):
    """创建受控修复提案（仅接受 completed run 中 severity=blocking、
    category=confirmed_drift 的真实 item；准入 + 防陈旧全过才生成 proposed）。"""
    if not isinstance(body, dict):
        body = {}
    run_id = body.get("run_id")
    item_key = body.get("item_key")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        return error_response(err.SDN_REMEDIATION_INVALID_ITEM, params={"item_key": "run_id"})
    if not isinstance(item_key, str) or not item_key.strip():
        return error_response(err.SDN_REMEDIATION_ITEM_NOT_FOUND, params={"item_key": item_key})
    item_key = item_key.strip()
    try:
        outcome = remed.create_proposal(
            db, vpc_id=vpc_id, run_id=run_id, item_key=item_key
        )
    except ProposalRejected as exc:
        return error_response(exc.error_key, params=exc.params)
    return APIResponse(
        success=True,
        data={
            "result": outcome["result"],
            "proposal": serialize_proposal(outcome["proposal"]),
        },
    )


@router.get("/vpcs/{vpc_id}/remediation-proposals", response_model=APIResponse)
def list_remediation_proposals(vpc_id: int, db: Session = Depends(get_db)):
    """列出该 VPC 的修复提案（读取时对每条 proposed 保守刷新陈旧状态）。"""
    rows = remed.list_proposals(db, vpc_id=vpc_id)
    return APIResponse(
        success=True,
        data={"vpc_id": vpc_id, "proposals": [serialize_proposal(r) for r in rows]},
    )


@router.get("/vpcs/{vpc_id}/remediation-proposals/{proposal_id}", response_model=APIResponse)
def get_remediation_proposal(vpc_id: int, proposal_id: int, db: Session = Depends(get_db)):
    """提案详情（proposed 在读取时经 CAS 保守刷新陈旧状态，绝不显示为可执行）。"""
    row = remed.get_proposal(db, vpc_id=vpc_id, proposal_id=proposal_id)
    if row is None:
        return error_response(
            err.SDN_REMEDIATION_NOT_FOUND,
            params={"vpc_id": vpc_id, "proposal_id": proposal_id},
        )
    return APIResponse(success=True, data=serialize_proposal(row))


@router.post("/vpcs/{vpc_id}/remediation-proposals/{proposal_id}/cancel", response_model=APIResponse)
def cancel_remediation_proposal(vpc_id: int, proposal_id: int, db: Session = Depends(get_db)):
    """取消提案（仅 proposed → cancelled 的 CAS；重复取消/已 stale 幂等返回当前行）。"""
    row = remed.cancel_proposal(db, vpc_id=vpc_id, proposal_id=proposal_id)
    if row is None:
        return error_response(
            err.SDN_REMEDIATION_NOT_FOUND,
            params={"vpc_id": vpc_id, "proposal_id": proposal_id},
        )
    return APIResponse(success=True, data=serialize_proposal(row))
