"""S2-001 VPC 目标态 / 观测态 / 差异投影（只读纯函数，零 I/O）。

把单个 VPC 在一台合格 EVPN Leaf 上的「平台期望 / 最近设备观测 / 二者差异」投影成
稳定、语言中性的结构，供 STRATA 直接消费。本模块：

- 不读写数据库、不触发 SSH/NETCONF、不写快照、不刷新任何时间戳；
- 只接受已序列化的事实（数据由 router 查库后传入），缺字段/畸形输入稳定降级，绝不抛异常；
- 目标态（desired）由「生命周期记录 + 当前版本因果」证明，而非「曾出现过记录」；
- 只比较现有快照能够可靠证明的维度：无证据 → ``unknown``，超出 TTL → ``stale``，
  相关性可证明时才 assert aligned/drifted；绝不以「执行记录」冒充「设备事实」。

诚实表达五条铁律：
1. 命令失败/缺失（``success != True`` 或 ``error``）同「无证据」，视为 ``unknown``，
   绝不把「采不到」降级成「不一致」（drifted）。
2. 远端 EVPN Type-2 / BGP 摘要不进本投影——只读本地 config 回读（VSI / VSI-interface /
   L3VNI / 接口 access-vlan|service-instance），绝不冒充本地下联端口或主机事实。
3. 目标存在性由 lifecycle 记录证明：成功且当前版本有效的 create → 期望存在；后续成功
   delete → 期望不存在；pending/failed/unknown 不覆盖最后一个确定结果；仅历史 snapshot /
   版本不一致 → desired 不武断 true，diff 不制造 drift。
4. 逐维 diff 附带稳定、脱敏的 ``evidence`` 指针（desired_source / observed_source），只含
   deployment/binding/snapshot 元数据与 display 命令名，绝不回传原始 CLI output/error/凭据。
5. ``aggregate`` 只是逐维状态的汇总（取「最差」），永不覆盖逐维事实。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Optional

# 观测快照新鲜度上限（秒）。与
# backend/app/services/sdn_operation_service.py 的 PREDEPLOY_EVIDENCE_MAX_AGE_SECONDS 及
# backend/app/services/sdn_validation_collector.py 的 DEFAULT_MIN_INTERVAL_SECONDS 对齐。
SNAPSHOT_TTL_SECONDS = 600

# ── 稳定状态枚举 ──
STATUS_ALIGNED = "aligned"
STATUS_DRIFTED = "drifted"
STATUS_UNKNOWN = "unknown"
STATUS_STALE = "stale"
STATUS_NOT_APPLICABLE = "not_applicable"

# 生命周期折叠结果
LIFECYCLE_PRESENT = "present"
LIFECYCLE_ABSENT = "absent"
LIFECYCLE_UNKNOWN = "unknown"

# ── 稳定 reason code（语言中性，供前端 i18n）──
RC_VSI_PRESENT = "vsi_present"
RC_VSI_MISSING = "vsi_missing"
RC_VSI_ABSENT = "vsi_absent"
RC_VSI_UNEXPECTED = "vsi_unexpected"
RC_VSI_UP = "vsi_up"
RC_VSI_DOWN = "vsi_down"
RC_VSI_IF_PRESENT = "vsi_interface_present"
RC_VSI_IF_MISSING = "vsi_interface_missing"
RC_VSI_IF_ABSENT = "vsi_interface_absent"
RC_VSI_IF_UNEXPECTED = "vsi_interface_unexpected"
RC_L3VNI_PRESENT = "l3_vni_present"
RC_L3VNI_MISSING = "l3_vni_missing"
RC_L3VNI_ABSENT = "l3_vni_absent"
RC_L3VNI_UNEXPECTED = "l3_vni_unexpected"
RC_SVC_PRESENT = "service_instance_present"
RC_SVC_MISSING = "service_instance_missing"
RC_VLAN_PRESENT = "access_vlan_present"
RC_VLAN_MISSING = "access_vlan_missing"
RC_NO_SNAPSHOT = "no_snapshot"
RC_EVIDENCE_MISSING = "evidence_missing"
RC_SNAPSHOT_STALE = "snapshot_stale"
RC_NOT_REQUIRED = "not_required"
RC_PLANNED_NOT_DEPLOYED = "planned_not_deployed"
RC_DESIRED_UNKNOWN = "desired_unknown"
RC_LIFECYCLE_CONFLICT = "lifecycle_conflict"

# 判定「该 Leaf 上应有 / 已部署端口绑定」的状态集合。
# planned 表「意图但尚未下发」：不进健康分母，也不断言其设备侧存在性（not_applicable）。
BINDING_OPERABLE_STATUSES = frozenset({"active", "expanding"})
BINDING_DESIRED_STATUSES = frozenset({"planned", "active", "expanding"})
CLI_ERROR_MARKERS = (
    "Incomplete command",
    "Unrecognized command",
    "Wrong parameter",
    "Too many parameters",
    "VPN-Instance does not exist",
)

# 目标态基础对象（VSI / VSI-interface / L3VNI）由这些 deployment action 决定。
BASE_CREATE_ACTION = "create"
BASE_DELETE_ACTION = "delete"
FULL_VPC_UNIT = "vpc-create-all"
GATEWAY_UNIT = "vsi-l3"
GATEWAY_DELETE_ACTION = "gateway_delete"


# ── 基础工具 ──


def _seconds_ago(collected_at: Any, now: datetime) -> Optional[float]:
    """collected_at 距 now 的秒数；无时间戳 → None（无法证明 stale）。"""
    if not isinstance(collected_at, datetime):
        return None
    try:
        return (now - collected_at).total_seconds()
    except TypeError:
        return None


def _commands(snapshot: Any) -> dict:
    """从快照解析出 ``{command: {success, output, error}}``；畸形 → {}。"""
    if not isinstance(snapshot, dict):
        return {}
    commands = snapshot.get("commands")
    return commands if isinstance(commands, dict) else {}


def _entry(commands: dict, cmd: str) -> Optional[dict]:
    entry = commands.get(cmd)
    return entry if isinstance(entry, dict) else None


def _observed_bool(commands: dict, cmd: str, predicate) -> Optional[bool]:
    """命令级观测：success==True 且无 error 才解析输出；否则 None（unknown）。"""
    entry = _entry(commands, cmd)
    if entry is None:
        return None
    if entry.get("success") is not True:
        return None
    if entry.get("error"):
        return None
    output = entry.get("output")
    if not isinstance(output, str):
        return None
    if any(marker in output for marker in CLI_ERROR_MARKERS):
        return None
    return bool(predicate(output))


def _observed_values(commands: dict, cmd: str, extractor) -> Optional[List[int]]:
    """命令级多值观测：success==True 且无 error 才解析为有序列表；否则 None（unknown）。"""
    entry = _entry(commands, cmd)
    if entry is None:
        return None
    if entry.get("success") is not True:
        return None
    if entry.get("error"):
        return None
    output = entry.get("output")
    if not isinstance(output, str):
        return None
    if any(marker in output for marker in CLI_ERROR_MARKERS):
        return None
    return extractor(output)


def _observed_evidence(snapshot_meta: dict, command: Optional[str]) -> Optional[dict]:
    """有快照记录 → 稳定观测指针（snapshot_id/collected_at/command）；无快照 → None。

    S2-003：只含稳定元数据，绝不携带原始 output/error/凭据。命令失败/畸形/过期仍保留
    指针（诚实说明「观测本应从何处来」），事实状态由 status/reason 表达。
    """
    if not isinstance(snapshot_meta, dict) or snapshot_meta.get("snapshot_id") is None:
        return None
    return {
        "kind": "snapshot",
        "snapshot_id": snapshot_meta.get("snapshot_id"),
        "collected_at": snapshot_meta.get("collected_at"),
        "command": command,
    }


def _evidence(desired_source: Optional[dict], observed_source: Optional[dict]) -> dict:
    """逐维证据指针：目标从哪来（deployment/binding/计数），设备事实从哪来（snapshot+command）。"""
    return {"desired_source": desired_source, "observed_source": observed_source}


def _classify_feature(desired: bool, observed: Optional[bool], *, stale: bool, unknown_rc: str, matched_rc: str, drifted_rc: str, evidence: dict) -> dict:
    if stale:
        return {"status": STATUS_STALE, "reason_code": RC_SNAPSHOT_STALE, "evidence": evidence}
    if observed is None:
        return {"status": STATUS_UNKNOWN, "reason_code": unknown_rc, "evidence": evidence}
    if observed == desired:
        return {"status": STATUS_ALIGNED, "reason_code": matched_rc, "evidence": evidence}
    return {"status": STATUS_DRIFTED, "reason_code": drifted_rc, "evidence": evidence}


def _classify_presence(
    desired_present: Optional[bool],
    observed: Optional[bool],
    *,
    stale: bool,
    unknown_rc: str,
    present_rc: str,
    absent_rc: str,
    missing_rc: str,
    unexpected_rc: str,
    evidence: dict,
) -> dict:
    """按目标存在性（True/False/None）对齐设备观测。

    - desired True  + observed True  → aligned(present)
    - desired True  + observed False → drifted(missing)
    - desired False + observed False → aligned(absent)
    - desired False + observed True  → drifted(unexpected，删了但设备仍残留)
    - desired None（证明不足）        → unknown，绝不 drift
    """
    if stale:
        return {"status": STATUS_STALE, "reason_code": RC_SNAPSHOT_STALE, "evidence": evidence}
    if desired_present is None:
        return {"status": STATUS_UNKNOWN, "reason_code": RC_DESIRED_UNKNOWN, "evidence": evidence}
    if observed is None:
        return {"status": STATUS_UNKNOWN, "reason_code": unknown_rc, "evidence": evidence}
    if desired_present is True:
        return {"status": STATUS_ALIGNED if observed else STATUS_DRIFTED, "reason_code": present_rc if observed else missing_rc, "evidence": evidence}
    # desired False（absent）
    return {"status": STATUS_ALIGNED if not observed else STATUS_DRIFTED, "reason_code": absent_rc if not observed else unexpected_rc, "evidence": evidence}


# ── 生命周期：目标态基础对象存在性（CR47）──


def _deployment_source(dep: Optional[dict]) -> Optional[dict]:
    if not isinstance(dep, dict):
        return None
    return {
        "kind": "deployment",
        "deployment_id": dep.get("id"),
        "action": dep.get("action"),
        "status": dep.get("status"),
        "version": dep.get("version"),
    }


def _resolve_lifecycle(deployments: Any, vpc_version: Any, *, gateway: bool) -> dict:
    """按维度折叠确定的配置生命周期。"""
    if not isinstance(deployments, list):
        deployments = []
    events = []
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue
        action = deployment.get("action")
        unit = deployment.get("unit")
        is_full = unit in (None, FULL_VPC_UNIT) and action in (BASE_CREATE_ACTION, BASE_DELETE_ACTION)
        is_gateway = unit == GATEWAY_UNIT and action in (BASE_CREATE_ACTION, GATEWAY_DELETE_ACTION)
        if is_full or (gateway and is_gateway):
            events.append(deployment)
    # 稳定排序：先 id 是否存在，再 id 升序（autoincrement 单调 = 受理顺序）。
    events.sort(key=lambda d: (d.get("id") is None, d.get("id") if isinstance(d.get("id"), int) else 0))

    last_create: Optional[dict] = None
    last_delete: Optional[dict] = None
    for d in events:
        if d.get("status") != "success":
            # pending/failed/unknown 不是确定结果，不得覆盖
            continue
        if d.get("action") == BASE_CREATE_ACTION:
            last_create = d
        else:
            last_delete = d

    if last_create is None:
        return {"state": LIFECYCLE_UNKNOWN, "source": None}

    if last_delete is not None and (last_delete.get("id") or 0) > (last_create.get("id") or 0):
        return {"state": LIFECYCLE_ABSENT, "source": _deployment_source(last_delete)}

    if last_create.get("version") != vpc_version:
        return {"state": LIFECYCLE_UNKNOWN, "source": _deployment_source(last_create)}

    return {"state": LIFECYCLE_PRESENT, "source": _deployment_source(last_create)}


def resolve_base_lifecycle(deployments: Any, vpc_version: Any) -> dict:
    """折叠 L2 VSI 生命周期；局部网关动作不得改变该结论。"""
    return _resolve_lifecycle(deployments, vpc_version, gateway=False)


def resolve_gateway_lifecycle(deployments: Any, vpc_version: Any) -> dict:
    """折叠 VSI-interface/L3VNI 生命周期，包含局部网关撤回与补回。"""
    return _resolve_lifecycle(deployments, vpc_version, gateway=True)


# ── 观测事实解析（严格区分 failed/absent → unknown，成功但内容不符 → drifted）──


def _vsi_command(vpc: dict) -> str:
    return f"display l2vpn vsi name {vpc.get('vsi_name')} verbose"


def _vsi_interface_command(vpc: dict) -> str:
    return f"display current-configuration interface Vsi-interface{vpc.get('vsi_interface')}"


def _binding_command(interface_name: str) -> str:
    return f"display current-configuration interface {interface_name}"


# CR49：token 精确匹配（行首/词边界），避免前缀串扰。
def _vsi_name_present(output: str, vsi_name: str) -> bool:
    return re.search(r"(?m)^\s*VSI Name\s*:\s*" + re.escape(str(vsi_name)) + r"\s*$", output) is not None


def _vsi_state_up(output: str) -> bool:
    return re.search(r"(?m)^\s*VSI State\s*:\s*Up\s*$", output) is not None


def _vsi_interface_present(output: str, vsi_interface: Any) -> bool:
    return (
        re.search(r"(?m)^\s*interface\s+Vsi-interface" + re.escape(str(vsi_interface)) + r"(?=\s|$)", output)
        is not None
    )


def _l3_vni_present(output: str, l3_vni: Any) -> bool:
    return re.search(r"(?m)\bl3-vni\s+" + re.escape(str(l3_vni)) + r"(?=\s|$)", output) is not None


def _service_instances(output: str) -> List[int]:
    return [int(m) for m in re.findall(r"\bservice-instance\s+(\d+)\b", output)]


def _access_vlans(output: str) -> List[int]:
    return [int(m) for m in re.findall(r"\bport access vlan\s+(\d+)\b", output)]


# ── 对外聚合 ──


def _aggregate_statuses(*statuses: str) -> str:
    """逐 status 取「最差」：stale > drifted > unknown > aligned；not_applicable 不计入。"""
    ordered = (STATUS_STALE, STATUS_DRIFTED, STATUS_UNKNOWN, STATUS_ALIGNED)
    present = {s for s in statuses if s != STATUS_NOT_APPLICABLE}
    for candidate in ordered:
        if candidate in present:
            return candidate
    return STATUS_UNKNOWN


def _desired_binding(binding: dict) -> dict:
    return {
        "binding_id": binding.get("id"),
        "if_index": binding.get("if_index"),
        "interface_name": binding.get("interface_name"),
        "access_vlan": binding.get("access_vlan"),
        "service_instance": binding.get("service_instance"),
        "status": binding.get("status"),
        "source": {
            "kind": "binding",
            "binding_id": binding.get("id"),
            "version": binding.get("version"),
        },
    }


def _binding_field_diff(value: Any, observed_values: Optional[List[int]], *, stale: bool, operable: bool, conflict: bool, column: str, evidence: dict) -> dict:
    """单个绑定字段（service_instance / access_vlan）的 diff。

    - conflict：基础对象已 delete 但绑定仍 operable → unknown/lifecycle_conflict，不选边。
    - 目标值精确属于观测集合 → aligned；否则 drifted。
    - 观测集合按有序列表返回，供 STRATA 复核；evidence 提供可下钻指针。
    """
    present_rc = RC_SVC_PRESENT if column == "service_instance" else RC_VLAN_PRESENT
    missing_rc = RC_SVC_MISSING if column == "service_instance" else RC_VLAN_MISSING
    if stale:
        return {"status": STATUS_STALE, "reason_code": RC_SNAPSHOT_STALE, "observed": None, "evidence": evidence}
    if conflict:
        return {"status": STATUS_UNKNOWN, "reason_code": RC_LIFECYCLE_CONFLICT, "observed": observed_values, "evidence": evidence}
    if not operable:
        return {"status": STATUS_NOT_APPLICABLE, "reason_code": RC_PLANNED_NOT_DEPLOYED, "observed": None, "evidence": evidence}
    if value is None:
        return {"status": STATUS_NOT_APPLICABLE, "reason_code": RC_NOT_REQUIRED, "observed": None, "evidence": evidence}
    if observed_values is None:
        return {"status": STATUS_UNKNOWN, "reason_code": RC_EVIDENCE_MISSING, "observed": None, "evidence": evidence}
    if value in observed_values:
        return {"status": STATUS_ALIGNED, "reason_code": present_rc, "observed": observed_values, "evidence": evidence}
    return {"status": STATUS_DRIFTED, "reason_code": missing_rc, "observed": observed_values, "evidence": evidence}


def build_leaf_projection(
    *,
    device: dict,
    vpc: dict,
    tenant: dict,
    bindings: list,
    deployments: list,
    snapshot: Any,
    snapshot_meta: dict,
    now: datetime,
) -> dict:
    """为单台合格 EVPN Leaf 构建 desired/observed/diff 投影。

    - device: 只读设备元数据 {"id", "name", "host", "sdn_role"}
    - vpc: {"id", "name", "version", "vni", "vsi_name", "vsi_interface"}
    - tenant: {"id", "l3_vni"}
    - bindings: 该 Leaf 上 (vpc) 的端口绑定列表（已序列化）
    - deployments: 该 Leaf 上 (vpc) 的 deployment 列表（已序列化；决定目标存在性）
    - snapshot: 解码后的 snapshot_data（可 None）
    - snapshot_meta: {"snapshot_id", "collected_at"}（无快照时为空 dict）
    - now: 注入的「当前时间」，便于确定性测试
    """
    device = device if isinstance(device, dict) else {}
    vpc = vpc if isinstance(vpc, dict) else {}
    tenant = tenant if isinstance(tenant, dict) else {}
    bindings = bindings if isinstance(bindings, list) else []
    deployments = deployments if isinstance(deployments, list) else []
    snapshot_meta = snapshot_meta if isinstance(snapshot_meta, dict) else {}

    commands = _commands(snapshot)
    has_snapshot_record = snapshot_meta.get("snapshot_id") is not None
    has_usable_commands = bool(commands)

    collected_at = snapshot_meta.get("collected_at")
    seconds_ago = _seconds_ago(collected_at, now) if has_usable_commands else None
    # 有命令但无采集时间戳 → 无法证明新鲜度，不判 stale（保守：不冒充新鲜，也不误判陈旧）。
    stale = bool(seconds_ago is not None and seconds_ago > SNAPSHOT_TTL_SECONDS)

    # unknown 的 reason：完全无快照记录 → no_snapshot；有记录但命令缺失/失败 → evidence_missing。
    unknown_rc = RC_EVIDENCE_MISSING if has_snapshot_record else RC_NO_SNAPSHOT

    vsi_name = vpc.get("vsi_name")
    vsi_interface = vpc.get("vsi_interface")
    l3_vni = tenant.get("l3_vni")
    vpc_version = vpc.get("version")

    # CR47：目标存在性由生命周期证明，而非「曾出现过记录」。
    lifecycle = resolve_base_lifecycle(deployments, vpc_version)
    gateway_lifecycle = resolve_gateway_lifecycle(deployments, vpc_version)
    base_state = lifecycle["state"]
    base_source = lifecycle["source"]
    gateway_state = gateway_lifecycle["state"]
    gateway_source = gateway_lifecycle["source"]

    operable = [b for b in bindings if b.get("status") in BINDING_OPERABLE_STATUSES]
    desired_bindings = [b for b in bindings if b.get("status") in BINDING_DESIRED_STATUSES]
    desired_vsi_up = bool(operable)
    # 基础对象已 delete 但仍有 operable 绑定 → 互相矛盾，诚实标 conflict。
    conflict = (base_state == LIFECYCLE_ABSENT) and bool(operable)

    base_present = (
        True if base_state == LIFECYCLE_PRESENT
        else False if base_state == LIFECYCLE_ABSENT
        else None
    )
    gateway_present = (
        True if gateway_state == LIFECYCLE_PRESENT
        else False if gateway_state == LIFECYCLE_ABSENT
        else None
    )

    observed_vsi = _observed_bool(commands, _vsi_command(vpc), lambda o: vsi_name is not None and _vsi_name_present(o, vsi_name))
    observed_vsi_up = _observed_bool(commands, _vsi_command(vpc), _vsi_state_up)
    observed_vsi_if = _observed_bool(commands, _vsi_interface_command(vpc), lambda o: vsi_interface is not None and _vsi_interface_present(o, vsi_interface))
    observed_l3vni = _observed_bool(commands, _vsi_interface_command(vpc), lambda o: l3_vni is not None and _l3_vni_present(o, l3_vni))

    # 逐绑定 diff（CR48：目标值精确属于观测集合，观测值按有序列表输出；S2-003：逐字段 evidence）
    binding_diffs = []
    for b in desired_bindings:
        iface = b.get("interface_name")
        operable_b = b.get("status") in BINDING_OPERABLE_STATUSES
        si_obs: Optional[List[int]] = None
        vlan_obs: Optional[List[int]] = None
        if has_usable_commands and iface:
            si_obs = _observed_values(commands, _binding_command(iface), _service_instances)
            vlan_obs = _observed_values(commands, _binding_command(iface), _access_vlans)
        b_cmd = _binding_command(iface) if iface else None
        b_desired_source = {"kind": "binding", "binding_id": b.get("id"), "version": b.get("version")}
        b_observed_evidence = _observed_evidence(snapshot_meta, b_cmd)
        binding_diffs.append(
            {
                "binding_id": b.get("id"),
                "interface_name": iface,
                "service_instance": _binding_field_diff(
                    b.get("service_instance"), si_obs, stale=stale, operable=operable_b, conflict=conflict, column="service_instance",
                    evidence=_evidence(b_desired_source, b_observed_evidence),
                ),
                "access_vlan": _binding_field_diff(
                    b.get("access_vlan"), vlan_obs, stale=stale, operable=operable_b, conflict=conflict, column="access_vlan",
                    evidence=_evidence(b_desired_source, b_observed_evidence),
                ),
            }
        )

    observed_section = None
    if has_snapshot_record:
        observed_section = {
            "snapshot_id": snapshot_meta.get("snapshot_id"),
            "collected_at": collected_at,
            "snapshot_age_seconds": (seconds_ago if seconds_ago is not None else None),
            "stale": stale,
            "facts": {
                "vsi_exists": observed_vsi,
                "vsi_up": observed_vsi_up,
                "vsi_interface_exists": observed_vsi_if,
                "l3_vni_present": observed_l3vni,
            },
        }

    vsi_cmd = _vsi_command(vpc)
    vsi_if_cmd = _vsi_interface_command(vpc)
    vsi_evidence = _evidence(base_source, _observed_evidence(snapshot_meta, vsi_cmd))
    gateway_evidence = _evidence(gateway_source, _observed_evidence(snapshot_meta, vsi_if_cmd))

    vsi_diff = _classify_presence(
        base_present, observed_vsi, stale=stale, unknown_rc=unknown_rc,
        present_rc=RC_VSI_PRESENT, absent_rc=RC_VSI_ABSENT, missing_rc=RC_VSI_MISSING, unexpected_rc=RC_VSI_UNEXPECTED,
        evidence=vsi_evidence,
    )
    vsi_if_diff = _classify_presence(
        gateway_present, observed_vsi_if, stale=stale, unknown_rc=unknown_rc,
        present_rc=RC_VSI_IF_PRESENT, absent_rc=RC_VSI_IF_ABSENT, missing_rc=RC_VSI_IF_MISSING, unexpected_rc=RC_VSI_IF_UNEXPECTED,
        evidence=gateway_evidence,
    )
    l3vni_diff = _classify_presence(
        gateway_present, observed_l3vni, stale=stale, unknown_rc=unknown_rc,
        present_rc=RC_L3VNI_PRESENT, absent_rc=RC_L3VNI_ABSENT, missing_rc=RC_L3VNI_MISSING, unexpected_rc=RC_L3VNI_UNEXPECTED,
        evidence=gateway_evidence,
    )

    vsi_up_desired_source = {"kind": "operable_binding_count", "count": len(operable)} if desired_vsi_up else None
    vsi_up_evidence = _evidence(vsi_up_desired_source, _observed_evidence(snapshot_meta, vsi_cmd))
    vsi_up_diff: dict
    if not desired_vsi_up:
        vsi_up_diff = {"status": STATUS_NOT_APPLICABLE, "reason_code": RC_NOT_REQUIRED, "evidence": vsi_up_evidence}
    elif conflict:
        vsi_up_diff = {"status": STATUS_UNKNOWN, "reason_code": RC_LIFECYCLE_CONFLICT, "evidence": vsi_up_evidence}
    else:
        vsi_up_diff = _classify_feature(True, observed_vsi_up, stale=stale, unknown_rc=unknown_rc, matched_rc=RC_VSI_UP, drifted_rc=RC_VSI_DOWN, evidence=vsi_up_evidence)

    statuses = [vsi_diff["status"], vsi_if_diff["status"], l3vni_diff["status"], vsi_up_diff["status"]]
    for bd in binding_diffs:
        statuses.append(bd["service_instance"]["status"])
        statuses.append(bd["access_vlan"]["status"])

    return {
        "device_id": device.get("id"),
        "device_name": device.get("name"),
        "device_host": device.get("host"),
        "sdn_role": device.get("sdn_role"),
        "desired": {
            "base": {
                "state": base_state,
                "source": base_source,
                "conflict": conflict,
            },
            "gateway": {
                "state": gateway_state,
                "source": gateway_source,
            },
            "vsi": {
                "present": base_present,
                "vsi_name": vsi_name,
                "source": base_source,
            },
            "vsi_interface": {
                "present": gateway_present,
                "vsi_interface": vsi_interface,
                "source": gateway_source,
            },
            "vsi_up": {
                "expected": desired_vsi_up,
                "source": {"kind": "operable_binding_count", "count": len(operable)},
            },
            "l3_vni": {
                "present": gateway_present,
                "l3_vni": l3_vni,
                "source": gateway_source,
            },
            "port_bindings": [_desired_binding(b) for b in desired_bindings],
        },
        "observed": observed_section,
        "diff": {
            "vsi": vsi_diff,
            "vsi_up": vsi_up_diff,
            "vsi_interface": vsi_if_diff,
            "l3_vni": l3vni_diff,
            "port_bindings": binding_diffs,
        },
        "aggregate": _aggregate_statuses(*statuses),
    }


def aggregate_vpc(leaf_statuses: list) -> str:
    """VPC 级汇总：各 Leaf aggregate 取最差；空集合 → unknown。"""
    return _aggregate_statuses(*list(leaf_statuses)) if leaf_statuses else STATUS_UNKNOWN


# ── S2-010 快照状态转变投影（只读、additive、保守语义）──
#
# 只表达相邻历史快照之间的“状态维度变化”，是证据状态转变，不是根因、物理拓扑、
# 转发路径，也不证明关联 operation 导致了变化。desired_basis 始终是 current_target
# （同一当前目标基准下的比较，不称历史目标差异）。

TRANSITION_UNCHANGED = "unchanged"
TRANSITION_DRIFT_DETECTED = "drift_detected"
TRANSITION_DRIFT_CLEARED = "drift_cleared"
TRANSITION_EVIDENCE_GAINED = "evidence_gained"
TRANSITION_EVIDENCE_LOST = "evidence_lost"
TRANSITION_STATE_CHANGED = "state_changed"
TRANSITION_BASELINE_UNAVAILABLE = "baseline_unavailable"

# 固定比较维度（同一 Leaf、同一 current_target 基准下逐维比较）。
TRANSITION_FIXED_DIMENSIONS = ("vsi", "vsi_up", "vsi_interface", "l3_vni")
# 按稳定 binding_id 匹配的绑定列（名称不是唯一身份）。
TRANSITION_BINDING_COLUMNS = ("service_instance", "access_vlan")

# 保守 transition 语义矩阵（按 from/to status）：
#   drifted → unknown/stale     只能 evidence_lost（不能称 drift_cleared）
#   unknown/stale → drifted     只能是 drift_detected
#   not_applicable 参与的变化   一律 state_changed（非漂移语义）
#   unknown ↔ stale（无漂移方向的状态变化）→ state_changed
#   aligned → unknown/stale     证据丢失 evidence_lost；unknown/stale → aligned 证据获得 evidence_gained
def _transition_kind(from_status: Optional[str], to_status: Optional[str]) -> str:
    if from_status == to_status:
        return TRANSITION_UNCHANGED
    if from_status is None or to_status is None:
        # 一侧维度不存在（如绑定只出现在其中一个快照）→ 存在性状态变化，不称漂移。
        return TRANSITION_STATE_CHANGED
    if from_status == STATUS_DRIFTED:
        if to_status in (STATUS_UNKNOWN, STATUS_STALE):
            return TRANSITION_EVIDENCE_LOST
        if to_status == STATUS_ALIGNED:
            return TRANSITION_DRIFT_CLEARED
        return TRANSITION_STATE_CHANGED
    if from_status in (STATUS_UNKNOWN, STATUS_STALE):
        if to_status == STATUS_DRIFTED:
            return TRANSITION_DRIFT_DETECTED
        if to_status == STATUS_ALIGNED:
            return TRANSITION_EVIDENCE_GAINED
        return TRANSITION_STATE_CHANGED
    if from_status == STATUS_ALIGNED:
        if to_status == STATUS_DRIFTED:
            return TRANSITION_DRIFT_DETECTED
        if to_status in (STATUS_UNKNOWN, STATUS_STALE):
            return TRANSITION_EVIDENCE_LOST
        return TRANSITION_STATE_CHANGED
    # 其余（含 not_applicable 参与的变化）→ state_changed
    return TRANSITION_STATE_CHANGED


def baseline_unavailable_transition(current: Optional[dict] = None) -> dict:
    """窗口最旧点的基线标记：明确无可用基线，绝不拿窗口外状态或当前实时状态补造。"""
    current = current if isinstance(current, dict) else {}
    return {
        "kind": TRANSITION_BASELINE_UNAVAILABLE,
        "desired_basis": "current_target",
        "baseline_unavailable": True,
        "from_snapshot_id": None,
        "to_snapshot_id": current.get("snapshot_id"),
        "from_collected_at": None,
        "to_collected_at": current.get("collected_at"),
        "dimensions": [],
        "summary": {
            "changed_dimensions": [],
            "counts": {TRANSITION_BASELINE_UNAVAILABLE: 1},
        },
    }


def build_transition(prior: dict, current: dict) -> dict:
    """比较同一 Leaf 相邻两个历史投影的逐维状态转变（S2-010，只读纯函数）。

    ``prior`` 为较旧点、``current`` 为较新点；两者都是 build_leaf_projection 的叶子投影
    字典（含 ``diff`` 与 ``aggregate``），且都基于同一 current_target。输入畸形/缺字段
    稳定降级（对应维度 from/to 取 None），绝不抛异常；只返回脱敏维度与摘要，不含原始
    CLI output/error/凭据。输出不宣称 operation 导致了变化。
    """
    prior = prior if isinstance(prior, dict) else {}
    current = current if isinstance(current, dict) else {}
    prior_diff = prior.get("diff") if isinstance(prior.get("diff"), dict) else {}
    current_diff = current.get("diff") if isinstance(current.get("diff"), dict) else {}

    dimensions: list[dict] = []
    for dim in TRANSITION_FIXED_DIMENSIONS:
        p_dim = prior_diff.get(dim) if isinstance(prior_diff.get(dim), dict) else {}
        c_dim = current_diff.get(dim) if isinstance(current_diff.get(dim), dict) else {}
        dimensions.append(
            {
                "dimension": dim,
                "from_status": p_dim.get("status"),
                "from_reason_code": p_dim.get("reason_code"),
                "to_status": c_dim.get("status"),
                "to_reason_code": c_dim.get("reason_code"),
                "transition": _transition_kind(p_dim.get("status"), c_dim.get("status")),
            }
        )

    # 绑定维度：按稳定 binding_id 匹配（不按显示名称）；两侧 binding 取并集保证顺序稳定。
    prior_bindings = {}
    for b in prior_diff.get("port_bindings") if isinstance(prior_diff.get("port_bindings"), list) else []:
        if isinstance(b, dict) and isinstance(b.get("binding_id"), int) and not isinstance(b.get("binding_id"), bool):
            prior_bindings[b["binding_id"]] = b
    current_bindings = {}
    for b in current_diff.get("port_bindings") if isinstance(current_diff.get("port_bindings"), list) else []:
        if isinstance(b, dict) and isinstance(b.get("binding_id"), int) and not isinstance(b.get("binding_id"), bool):
            current_bindings[b["binding_id"]] = b
    for binding_id in sorted(set(prior_bindings) | set(current_bindings)):
        p_binding = prior_bindings.get(binding_id, {})
        c_binding = current_bindings.get(binding_id, {})
        for col in TRANSITION_BINDING_COLUMNS:
            p_field = p_binding.get(col) if isinstance(p_binding.get(col), dict) else {}
            c_field = c_binding.get(col) if isinstance(c_binding.get(col), dict) else {}
            dimensions.append(
                {
                    "dimension": f"binding:{binding_id}:{col}",
                    "binding_id": binding_id,
                    "column": col,
                    "from_status": p_field.get("status"),
                    "from_reason_code": p_field.get("reason_code"),
                    "to_status": c_field.get("status"),
                    "to_reason_code": c_field.get("reason_code"),
                    "transition": _transition_kind(p_field.get("status"), c_field.get("status")),
                }
            )

    # 脱敏摘要：变更维度清单 + 按 kind 计数（不含任何原始证据）。
    changed_dimensions = [d["dimension"] for d in dimensions if d["transition"] != TRANSITION_UNCHANGED]
    counts: dict = {}
    for d in dimensions:
        counts[d["transition"]] = counts.get(d["transition"], 0) + 1
    return {
        "kind": "transition",
        "desired_basis": "current_target",
        "from_snapshot_id": prior.get("snapshot_id"),
        "to_snapshot_id": current.get("snapshot_id"),
        "from_collected_at": prior.get("collected_at"),
        "to_collected_at": current.get("collected_at"),
        "dimensions": dimensions,
        "summary": {
            "changed_dimensions": changed_dimensions,
            "counts": counts,
        },
    }


# ── S2-012 VPC EVPN Leaf 范围覆盖投影（只读、additive、保守分类）──
#
# 范围不是健康度：未覆盖/已撤回/证据不足都是范围事实，不得自动冒充故障或漂移。
# 只枚举 sdn_role=evpn_leaf 设备（不按名称/platform 推断）；复用 resolve_base_lifecycle
# 同一生命周期判定，不复制一套；snapshot 单独不能证明 targeted；历史成功 create 版本
# 不匹配仍 ambiguous；failed/pending 不覆盖确定生命周期；局部 gateway_delete 不改变
# base 范围。

SCOPE_TARGETED = "targeted"
SCOPE_WITHDRAWN = "withdrawn"
SCOPE_NOT_TARGETED = "not_targeted"
SCOPE_AMBIGUOUS = "ambiguous"
SCOPE_CLASSIFICATIONS = (SCOPE_TARGETED, SCOPE_WITHDRAWN, SCOPE_NOT_TARGETED, SCOPE_AMBIGUOUS)


def build_scope_member(device: dict, *, deployments: Any, bindings: Any, snapshot_count: Any, vpc_version: Any) -> dict:
    """单台 EVPN Leaf 相对某 VPC 的范围分类（S2-012，只读纯函数，绝不抛异常）。

    - ``targeted``：当前版本生命周期可证明 base present，或存在 planned/active/expanding
      当前目标绑定（reason_code: base_present / current_target_binding）；
    - ``withdrawn``：生命周期可证明 base absent 且无当前目标绑定（base_absent）；
    - ``not_targeted``：该 VPC 对此 Leaf 无 deployment/binding/snapshot 记录（no_records）；
    - ``ambiguous``：有历史记录，但当前生命周期不能证明 present/absent 且无当前目标
      绑定（lifecycle_unproven）。

    只返回白名单字段（device_id/name/host、classification、reason_code、record_sources、
    desired_base_state、desired_binding_count），不回传凭据/原始配置/快照；输入畸形/
    缺字段稳定降级不抛异常。
    """
    device = device if isinstance(device, dict) else {}
    deployments = [d for d in (deployments if isinstance(deployments, list) else []) if isinstance(d, dict)]
    bindings = [b for b in (bindings if isinstance(bindings, list) else []) if isinstance(b, dict)]
    if isinstance(snapshot_count, bool) or not isinstance(snapshot_count, int):
        snapshot_count = 0
    base = resolve_base_lifecycle(deployments, vpc_version)
    desired_bindings = [b for b in bindings if b.get("status") in BINDING_DESIRED_STATUSES]
    records_exist = bool(deployments) or bool(bindings) or snapshot_count > 0
    if base.get("state") == LIFECYCLE_PRESENT or desired_bindings:
        classification = SCOPE_TARGETED
        reason_code = "base_present" if base.get("state") == LIFECYCLE_PRESENT else "current_target_binding"
    elif base.get("state") == LIFECYCLE_ABSENT:
        classification = SCOPE_WITHDRAWN
        reason_code = "base_absent"
    elif not records_exist:
        classification = SCOPE_NOT_TARGETED
        reason_code = "no_records"
    else:
        classification = SCOPE_AMBIGUOUS
        reason_code = "lifecycle_unproven"
    return {
        "device_id": device.get("id"),
        "name": device.get("name"),
        "host": device.get("host"),
        "classification": classification,
        "reason_code": reason_code,
        "record_sources": {
            "deployment": {"present": bool(deployments), "count": len(deployments)},
            "binding": {"present": bool(bindings), "count": len(bindings)},
            "snapshot": {"present": snapshot_count > 0, "count": snapshot_count},
        },
        "desired_base_state": base.get("state"),
        "desired_binding_count": len(desired_bindings),
    }
