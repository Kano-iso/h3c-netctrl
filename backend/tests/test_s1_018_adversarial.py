"""S1-018 对抗性测试：Type-3 证据按目标 VPC 的 Route distinguisher 归属校验（CR38）。

这些断言在 S1-017 现状上会失败：`_validate` 仍用 `"[3]" in bgp_evpn_text` 判定 type3_present，
只能证明设备上存在任意 VPC 的 Type-3，不能证明目标 VPC 的 Type-3——当目标 VPC 缺 Type-3、
另一个 VPC 有 Type-3 时会错误放行 terminal 接入。

修复后：只在目标 `Route distinguisher: 1:{vpc.vni}` 路由块中发现 `[3]` 才令 type3_present.ok=True；
多 RD 正确分块；1:2000 与 1:20000 不得串匹配；目标 RD 缺失/只有 [2]/无法解析 → 保守 false。
"""
import json

import pytest

from app.models import SdnValidationSnapshot
from app.services.sdn_validation_collector import SdnValidationCollector
from app.routers.sdn_access import _l2_ready_status

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from test_sdn_access_api import _seed_ready  # noqa: E402


def _latest_snap(db, vpc):
    return (
        db.query(SdnValidationSnapshot)
        .filter(SdnValidationSnapshot.vpc_id == vpc.id)
        .order_by(SdnValidationSnapshot.id.desc())
        .first()
    )


# ── _type3_scoped 单元测试（目标 RD 归属判定）──

def test_type3_scoped_target_rd_has_type3_true():
    text = (
        "Route distinguisher: 1:2000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 2000) is True


def test_type3_scoped_other_rd_type3_target_type2_false():
    text = (
        "Route distinguisher: 1:3000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
        "Route distinguisher: 1:2000\n"
        "* >  Network : [2][0][48][96ba-e5f7-0a06][0][0.0.0.0]/104\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 2000) is False


def test_type3_scoped_target_rd_missing_false():
    text = (
        "Route distinguisher: 1:3000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 2000) is False


def test_type3_scoped_vni_substring_no_false_match():
    # 目标 vni=2000，但输出只有 1:20000 的 [3]——不得用裸子串让 1:2000 命中 1:20000
    text = (
        "Route distinguisher: 1:20000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 2000) is False


def test_type3_scoped_multi_rd_target_middle_true():
    text = (
        "Route distinguisher: 1:1000\n"
        "* >  Network : [3][0][32][9.9.9.9]/80\n"
        "Route distinguisher: 1:2000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
        "Route distinguisher: 1:3000\n"
        "* >  Network : [3][0][32][2.2.2.2]/80\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 2000) is True


def test_type3_scoped_multi_rd_target_last_true():
    text = (
        "Route distinguisher: 1:1000\n"
        "* >  Network : [3][0][32][9.9.9.9]/80\n"
        "Route distinguisher: 1:2000\n"
        "* >  Network : [2][0][48][96ba-e5f7-0a06][0][0.0.0.0]/104\n"
        "Route distinguisher: 1:3000\n"
        "* >  Network : [3][0][32][1.1.1.4]/80\n"
    )
    assert SdnValidationCollector._type3_scoped(text, 3000) is True


# ── 真实 collector._validate 端到端（S1-017 会错误返回 ok=True）──

def test_validate_type3_is_scoped_to_target_rd(db):
    device, _, vpc = _seed_ready(None, db)
    bgp_evpn = (
        "Route distinguisher: 1:9999\n"
        "* >  Network : [3][0][32][9.9.9.9]/80\n"
        f"Route distinguisher: 1:{vpc.vni}\n"
        "* >  Network : [2][0][48][96ba-e5f7-0a06][0][0.0.0.0]/104\n"
    )
    snap_data = {"commands": {
        "display bgp l2vpn evpn": {"success": True, "output": bgp_evpn, "error": None},
    }}
    details = SdnValidationCollector._validate(vpc, [], snap_data)
    assert details["type3_present"]["ok"] is False


# ── terminal L2 门禁：目标 RD 无 Type-3 → unknown ──

def test_terminal_gate_unknown_when_type3_not_in_target_rd(db):
    device, _, vpc = _seed_ready(None, db)
    snap = _latest_snap(db, vpc)
    snap_data = json.loads(snap.snapshot_data)
    snap_data["commands"]["display bgp l2vpn evpn"]["output"] = (
        "Route distinguisher: 1:9999\n"
        "* >  Network : [3][0][32][9.9.9.9]/80\n"
        f"Route distinguisher: 1:{vpc.vni}\n"
        "* >  Network : [2][0][48][96ba-e5f7-0a06][0][0.0.0.0]/104\n"
    )
    # 用真实 _validate 重算 details（其他命令保持 seed 的健康输出，L2 命令完整）
    details = SdnValidationCollector._validate(vpc, [], snap_data)
    snap.validation_details = json.dumps(details)
    db.commit()
    status, detail = _l2_ready_status(db, vpc, device.id)
    assert status == "unknown"
    assert "type3_present" in detail
