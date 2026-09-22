"""S1-026 operation 解释投影（只读 serializer 纯函数）。

把 operation / attempt / unit 的持久化事实翻译成稳定、语言中性的 `explanation`
投影，供 NEXT 工作台 PULSE / STRATA 消费。本模块不读写数据库、不触发设备 I/O、
不改写任何执行语义；所有函数对缺字段 / 畸形输入稳定降级，绝不抛异常。

诚实表达约定：
- 无法从真实数据证明的字段一律返回 ``None``（null），禁止编造。
- ``succeeded`` 单元若无观察证据，只表达「执行记录成功」，不冒充「设备已验证成功」。
- truth_kind 枚举：``desired | observed | inferred | pending``；中文展示由前端 i18n
  完成，本模块只返回稳定 code 与简短、语言中性的 fallback statement。
"""

from __future__ import annotations

from typing import Any, Optional

# ── 稳定 code 映射（语言中性，供前端 i18n key 使用） ──

OPERATION_INTENT = {
    "terminal_access": "access_bind",
    "terminal_withdraw": "access_unbind",
    "legacy_apply": "legacy_apply",
}

ATTEMPT_SUMMARY = {
    "execute": "execute configuration on device",
    "validate": "validate against device state",
    "withdraw": "withdraw access binding",
    "reconcile": "reconcile uncertain outcome from device readback",
}

# truth_kind：desired（期望/记录）/ observed（设备观测）/ inferred（推断）/ pending（未定）
TRUTH_DESIRED = "desired"
TRUTH_OBSERVED = "observed"
TRUTH_INFERRED = "inferred"
TRUTH_PENDING = "pending"

PENDING_OPERATION_STATUSES = frozenset(
    {
        "planned",
        "claimed",
        "awaiting_wiring",
        "applying",
        "awaiting_validation",
        "validating",
        "withdrawing",
        "reconciling",
    }
)

UNCERTAIN_ATTEMPT_STATUSES = frozenset({"claimed", "running", "unknown"})


# ── 基础工具 ──


def _s(value: Any) -> Optional[str]:
    """稳定字符串化；None / 非文本 / 空白 → None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value if value.strip() else None
    return None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _truth_state(status: str, attempts: list[dict]) -> str:
    """operation 级 truth_state：区分「执行记录成功」与「设备验证成功」。"""
    if status == "succeeded":
        # 仅当存在确定完成的 validate attempt 才称得上 device-verified。
        for a in attempts:
            if a.get("kind") == "validate" and a.get("status") == "succeeded":
                return "verified"
        return "succeeded_recorded"
    if status == "degraded":
        return "degraded"
    if status == "failed":
        return "failed"
    if status == "withdrawn":
        return "withdrawn"
    if status == "unknown":
        return "unknown"
    if status in PENDING_OPERATION_STATUSES:
        return "pending"
    return status or "unknown"


def _operation_ambiguous(status: str, attempts: list[dict]) -> bool:
    """当前 claims 是否处于不确定/歧义。

    历史 stale takeover / 证据不足只解释对应 attempt；一旦 operation 已进入
    确定终态，不能再把历史不确定性冒充为当前 claim 歧义。
    """
    if status == "unknown":
        return True
    if status in {"succeeded", "degraded", "failed", "withdrawn", "applied"}:
        return False
    for a in attempts:
        ev = _dict(a.get("evidence"))
        if ev.get("stale_takeover") is True:
            return True
        dims = _dict(ev.get("dimensions"))
        evidence = _dict(dims.get("evidence"))
        if evidence.get("status") == "insufficient":
            return True
    return False


def _scope_summary(scope: Optional[dict], expected_host_ip: Any) -> Optional[str]:
    """从 scope + expected_host_ip 生成紧凑、语言中性的范围摘要；无数据 → None。"""
    if not isinstance(scope, dict) or not scope:
        return None
    parts = []
    for key, label in (("tenant_name", "tenant"), ("vpc_name", "vpc"), ("device_name", "device")):
        v = _s(scope.get(key))
        if v:
            parts.append(f"{label}={v}")
    iface = _s(scope.get("interface_name"))
    if iface:
        idx = scope.get("if_index")
        parts.append(f"if={iface}({idx if idx is not None else '?'})")
    vlan = scope.get("access_vlan")
    if vlan is not None:
        parts.append(f"vlan={vlan}")
    svc = scope.get("service_instance")
    if svc is not None:
        parts.append(f"svc={svc}")
    host = _s(expected_host_ip)
    if host:
        parts.append(f"host={host}")
    return " ".join(parts) if parts else None


def _target(scope: Optional[dict]) -> Optional[dict]:
    """操作目标对象（device/if_index/interface）；无范围数据 → None。"""
    if not isinstance(scope, dict):
        return None
    device_id = scope.get("device_id")
    if_index = scope.get("if_index")
    iface = _s(scope.get("interface_name"))
    if device_id is None and if_index is None and iface is None:
        return None
    return {
        "device_id": device_id if device_id is not None else None,
        "if_index": if_index if if_index is not None else None,
        "interface_name": iface,
    }


def _headline(intent: str, target: Optional[dict], truth_state: str) -> str:
    if target and target.get("interface_name"):
        return f"{intent} {target['interface_name']} {truth_state}"
    return f"{intent} {truth_state}"


def _evidence_basis(kind: str, evidence: dict) -> Optional[str]:
    """attempt 证据形态的稳定 code；无证据 → None。"""
    if evidence.get("stale_takeover") is True:
        return "stale_takeover"
    dims = _dict(evidence.get("dimensions"))
    if isinstance(evidence.get("dimensions"), dict) and dims:
        evidence_dim = _dict(dims.get("evidence"))
        if evidence_dim.get("status") == "insufficient":
            return "insufficient_evidence"
        return "four_dimension_validation"
    if kind in ("execute", "withdraw"):
        return "execution_record"
    if kind == "reconcile":
        return "reconciliation"
    return None


# ── 对外纯函数 ──


def explain_operation(operation: dict, scope: Optional[dict], attempts: Optional[list] = None) -> dict:
    """operation 级解释投影。输入为已序列化的 operation 字典 + scope dict + attempt 摘要列表。

    attempts 元素仅需 ``{"kind", "status", "evidence"}``（用于判定 device-verified /
    claims 歧义）；缺失时按无 attempt 处理，稳定降级。主参为 None/畸形时同样降级，绝不抛出。
    """
    operation = _dict(operation)
    attempts = attempts if isinstance(attempts, list) else []
    op_type = _s(operation.get("operation_type")) or "unknown"
    status = _s(operation.get("status")) or "unknown"
    intent = OPERATION_INTENT.get(op_type, op_type)
    scope_summary = _scope_summary(scope, operation.get("expected_host_ip"))
    target = _target(scope)
    ambiguous = _operation_ambiguous(status, attempts)
    truth_state = _truth_state(status, attempts)
    target_only = op_type in ("terminal_access", "terminal_withdraw")
    return {
        "intent": intent,
        "statement": f"operation {op_type}: {truth_state}",
        "scope_summary": scope_summary,
        "safety_boundary": {
            "target": target,
            "target_only": target_only,
            "ambiguous_claims": ambiguous,
            "protected_interfaces": None,  # 未持久化于 operation → null（禁止编造）
        },
        "truth_state": truth_state,
        "headline": _headline(intent, target, truth_state),
    }


def explain_attempt(attempt: dict) -> dict:
    """attempt 级解释投影。输入已序列化 attempt 字典（含 evidence）。主参畸形时稳定降级。"""
    attempt = _dict(attempt)
    kind = _s(attempt.get("kind")) or "unknown"
    status = _s(attempt.get("status")) or "unknown"
    finished = bool(attempt.get("completed_at"))
    evidence = _dict(attempt.get("evidence"))
    basis = _evidence_basis(kind, evidence)
    # failed_known 是确定结论（失败也是确定），不算「仍不确定」。
    still_uncertain = status in UNCERTAIN_ATTEMPT_STATUSES
    statement = _attempt_statement(kind, status, basis)
    return {
        "kind": kind,
        "summary": ATTEMPT_SUMMARY.get(kind, kind),
        "result": status,
        "finished": finished,
        "still_uncertain": still_uncertain,
        "evidence_basis": basis,
        "statement": statement,
        "started_at": attempt.get("started_at"),
        "completed_at": attempt.get("completed_at"),
    }


def _attempt_statement(kind: str, status: str, basis: Optional[str]) -> str:
    if basis == "insufficient_evidence":
        return "validation could not collect sufficient device evidence"
    if status == "succeeded":
        return f"{kind} succeeded"
    if status == "failed_known":
        return f"{kind} finished with known failure"
    if status == "unknown":
        return f"{kind} outcome uncertain"
    if status in ("claimed", "running"):
        return f"{kind} in progress"
    return f"{kind} {status}"


def explain_unit(unit: dict, attempt_kind: str = "execute", attempt_scope: Optional[dict] = None) -> dict:
    """unit 级解释投影。输入已序列化 unit 字典（含 evidence）+ 所属 attempt kind/scope。

    无法证明的字段（freshness 等）一律返回 null；succeeded 无观察证据只表达执行记录成功。
    主参畸形时稳定降级，绝不抛出。
    """
    unit = _dict(unit)
    state = _s(unit.get("state")) or "not_started"
    evidence = _dict(unit.get("evidence"))
    unit_name = _s(unit.get("unit_name"))
    scope = attempt_scope if isinstance(attempt_scope, dict) and attempt_scope else None

    expl: dict[str, Any] = {
        "category": None,
        "statement": None,
        "truth_kind": TRUTH_PENDING,
        "source": None,
        "scope": scope,
        "observed_at": None,
        "freshness": None,  # 单元级无独立时效时间戳 → null（handoff 登记缺口）
    }

    if state == "succeeded":
        if evidence.get("reconciled") is True:
            if attempt_kind == "withdraw":
                # 解绑对账：结构化语法匹配证明配置缺失 → 推断而非直接观测
                expl.update(
                    category="readback_syntax_match",
                    truth_kind=TRUTH_INFERRED,
                    source="snapshot",
                    observed_at=unit.get("completed_at"),
                    statement="readback syntax match confirms configuration removal",
                )
            else:
                expl.update(
                    category="readback_verified",
                    truth_kind=TRUTH_OBSERVED,
                    source="snapshot",
                    observed_at=unit.get("completed_at"),
                    statement="readback confirmed device state",
                )
        else:
            # 无观察证据：只表达执行记录成功（诚实表达，不冒充设备验证）
            expl.update(
                category="execution_record",
                truth_kind=TRUTH_DESIRED,
                source="execution_record",
                observed_at=None,
                statement="unit executed successfully (recorded; not device-verified)",
            )
    elif state == "failed_known":
        if evidence.get("reconciled") is True:
            expl.update(
                category="readback_verified_failure",
                truth_kind=TRUTH_OBSERVED,
                source="snapshot",
                observed_at=unit.get("completed_at"),
                statement="readback confirmed failure",
            )
        else:
            err_msg = _s(evidence.get("error"))
            if evidence.get("definitive") is True:
                # 确定性失败：设备明确拒绝 → 设备响应观测
                expl.update(
                    category="device_rejection",
                    truth_kind=TRUTH_OBSERVED,
                    source="device_response",
                    observed_at=unit.get("completed_at"),
                    statement=f"unit failed: {err_msg}" if err_msg else "unit failed",
                )
            else:
                expl.update(
                    category="failure_uncertain",
                    truth_kind=TRUTH_PENDING,
                    source="execution_record",
                    observed_at=unit.get("completed_at"),
                    statement=f"unit failed (uncertain): {err_msg}" if err_msg else "unit failed (uncertain)",
                )
    elif state == "unknown":
        expl.update(
            category="uncertain_outcome",
            truth_kind=TRUTH_PENDING,
            source=None,
            observed_at=unit.get("completed_at"),
            statement="outcome uncertain",
        )
    elif state == "started":
        expl.update(
            category="in_progress",
            truth_kind=TRUTH_PENDING,
            source=None,
            observed_at=unit.get("started_at"),
            statement="unit started; no terminal state",
        )
    else:  # not_started
        expl.update(
            category="not_finished",
            truth_kind=TRUTH_PENDING,
            source=None,
            observed_at=None,
            statement="unit not started",
        )
    return expl


# ── S2-008 多对象变更影响投影（只读、additive、复用同一 truth 系统）──

# 关系名只表达 operation scope 中可证明的业务范围，不是真实物理邻接 / 实时转发路径 /
# 因果链：vpc targets device、device exposes interface；interface 对 host 的语义按
# operation type 区分（access 期望主机 expects / withdraw 撤回或移除目标 withdraws；
# legacy 无法证明则不编造关系）。
IMPACT_RELATION_TARGETS = "targets"
IMPACT_RELATION_EXPOSES = "exposes"
IMPACT_RELATION_EXPECTS = "expects"
IMPACT_RELATION_WITHDRAWS = "withdraws"

# 接口稳定复合身份：device identity + if_index（跨 Leaf 不碰撞）；scope 缺 device 时
# 不编造全局接口身份（id 为 null，可读字段仍保留）。
IMPACT_IFACE_ID_TEMPLATE = "device:{device_id}:if_index:{if_index}"


def _impact_node(kind: str, node_id: Any, label: Optional[str], source: str) -> dict:
    return {
        "kind": kind,
        "id": node_id,
        "label": label,
        "truth_kind": TRUTH_DESIRED,  # 节点来自 operation 记录/scope（记录的目标），非设备观测
        "source": source,
    }


def _impact_relation(from_kind: str, from_id: Any, relation: str, to_kind: str, to_id: Any) -> dict:
    return {
        "from_kind": from_kind,
        "from_id": from_id,
        "relation": relation,
        "to_kind": to_kind,
        "to_id": to_id,
    }


def _find_node(nodes: list, kind: str) -> Optional[dict]:
    for n in nodes:
        if n["kind"] == kind:
            return n
    return None


def build_operation_impact(
    operation: dict,
    scope: Optional[dict],
    attempts: Optional[list] = None,
    explanation: Optional[dict] = None,
    attempt_facts: Optional[list] = None,
) -> dict:
    """operation 级多对象变更影响投影（S2-008，只读纯函数，绝不抛异常）。

    输入已序列化 operation 字典 + scope dict + attempt_data 列表（每 attempt 须含
    已计算的 ``explanation`` 与每 unit 的 ``explanation``），以及可选的 explain_operation
    输出（用于复用同一 truth 判定）。未传 explanation 时调用既有 ``explain_operation``
    （从真实 attempt facts 组装），绝不另写简化判定；主参畸形/缺字段稳定降级。

    - 节点：VPC / 目标 EVPN Leaf / 目标接口 / 期望主机，仅持久化字段出现时出现；缺失
      字段为 null，不编造；以稳定 id 为身份（接口为 device+if_index 复合身份），名称只
      是 label，不把名称当唯一身份；source 如实区分 operation_scope / operation_record。
    - 关系：只表达 scope 可证明的业务范围（targets / exposes；interface→host 按操作类型
      取 expects / withdraws），不称物理邻接；legacy 无法证明则不编造。
    - 变更项：按 attempt/unit 持久化顺序输出，truth_kind/source/statement 直接复用
      explain_attempt/explain_unit 已计算的解释（同一 truth 系统，无第二套真假判定）。
    - safety：target_only / ambiguous_claims 复用 explain_operation 判定（含 attempt 中
      stale_takeover / insufficient evidence 的歧义）；共享 VPC/网关不属于 terminal
      access/withdraw 的操作目标（既有受控边界）；无法证明的 protected list 仍为 null。
    """
    operation = _dict(operation)
    scope = scope if isinstance(scope, dict) and scope else {}
    attempts = attempts if isinstance(attempts, list) else []
    explanation = explanation if isinstance(explanation, dict) and explanation else {}

    op_type = _s(operation.get("operation_type")) or "unknown"
    op_vpc_id = operation.get("vpc_id")
    op_device_id = operation.get("device_id")
    expected_host_ip = _s(operation.get("expected_host_ip"))

    # ── 节点（顺序稳定：vpc → device → interface → host；按 (kind, id) 去重；
    #    source 如实区分 operation_scope 与 operation_record）──
    nodes: list[dict] = []
    sc_vpc_id = scope.get("vpc_id")
    vpc_id_value = sc_vpc_id if sc_vpc_id is not None else op_vpc_id
    vpc_source = "operation_scope" if sc_vpc_id is not None else ("operation_record" if op_vpc_id is not None else None)
    if vpc_id_value is not None:
        nodes.append(_impact_node("vpc", vpc_id_value, _s(scope.get("vpc_name")), vpc_source))

    sc_device_id = scope.get("device_id")
    device_id_value = sc_device_id if sc_device_id is not None else op_device_id
    device_source = "operation_scope" if sc_device_id is not None else ("operation_record" if op_device_id is not None else None)
    if device_id_value is not None:
        nodes.append(_impact_node("device", device_id_value, _s(scope.get("device_name")), device_source))

    if_index = scope.get("if_index")
    interface_name = _s(scope.get("interface_name"))
    if if_index is not None or interface_name:
        # 稳定复合接口身份：scope 声明的 device identity + if_index；scope 缺 device 时
        # 不编造全局接口身份（id 为 null，可读字段仍保留）——op 记录的 device_id 不能
        # 证明接口归属该设备，不得借用来拼身份。
        iface_id = None
        if sc_device_id is not None and if_index is not None:
            iface_id = IMPACT_IFACE_ID_TEMPLATE.format(device_id=sc_device_id, if_index=if_index)
        nodes.append(
            {
                "kind": "interface",
                "id": iface_id,
                "label": interface_name,
                "device_id": sc_device_id if sc_device_id is not None else None,
                "if_index": if_index if if_index is not None else None,
                "interface_name": interface_name,
                "truth_kind": TRUTH_DESIRED,
                "source": "operation_scope",
            }
        )

    if expected_host_ip:
        nodes.append(_impact_node("host", expected_host_ip, expected_host_ip, "operation_record"))

    # ── 关系（仅两端节点都有稳定身份时出现；接口端点引用同一复合身份）──
    relations: list[dict] = []
    vpc_node = _find_node(nodes, "vpc")
    device_node = _find_node(nodes, "device")
    iface_node = _find_node(nodes, "interface")
    host_node = _find_node(nodes, "host")
    if vpc_node and device_node:
        relations.append(_impact_relation("vpc", vpc_node["id"], IMPACT_RELATION_TARGETS, "device", device_node["id"]))
    if device_node and iface_node and iface_node.get("id") is not None:
        relations.append(_impact_relation("device", device_node["id"], IMPACT_RELATION_EXPOSES, "interface", iface_node["id"]))
    # interface→host 语义按操作类型区分；legacy 无法证明则不编造。
    host_relation = None
    if op_type == "terminal_access":
        host_relation = IMPACT_RELATION_EXPECTS
    elif op_type == "terminal_withdraw":
        host_relation = IMPACT_RELATION_WITHDRAWS
    if host_relation and iface_node and iface_node.get("id") is not None and host_node:
        relations.append(_impact_relation("interface", iface_node["id"], host_relation, "host", host_node["id"]))

    # ── 变更项：attempt/unit 持久化顺序；truth_kind/source/statement 复用已有解释 ──
    changes: list[dict] = []
    for a0 in attempts:
        a = _dict(a0)
        unit_items = []
        units = a.get("units") if isinstance(a.get("units"), list) else []
        for u0 in units:
            u = _dict(u0)
            u_expl = _dict(u.get("explanation"))
            unit_items.append(
                {
                    "unit_index": u.get("unit_index"),
                    "unit_name": _s(u.get("unit_name")),
                    "state": _s(u.get("state")) or "not_started",
                    "truth_kind": u_expl.get("truth_kind"),
                    "source": u_expl.get("source"),
                    "statement": u_expl.get("statement"),
                }
            )
        changes.append(
            {
                "attempt_id": a.get("attempt_id"),
                "attempt_kind": _s(a.get("kind")) or "unknown",
                "units": unit_items,
            }
        )

    # ── safety：复用 explain_operation 的 truth 判定（同源）；未传 explanation 时用
    #    真实 attempt facts 调用既有 explain_operation，绝不另写简化判定 ──
    boundary = _dict(explanation.get("safety_boundary"))
    if not boundary:
        facts = attempt_facts if isinstance(attempt_facts, list) else []
        boundary = _dict(explain_operation(operation, scope if scope else None, facts).get("safety_boundary"))
    target_only = boundary.get("target_only")
    ambiguous_claims = boundary.get("ambiguous_claims")
    # 既有受控边界：共享 VPC/网关对象不属于 terminal access/withdraw 的操作目标；
    # legacy_apply 无法证明该边界 → null，不编造。
    shared_vpc_gateway_not_target = True if target_only else None

    return {
        "nodes": nodes,
        "relations": relations,
        "changes": changes,
        "safety": {
            "target_only": target_only,
            "ambiguous_claims": ambiguous_claims,
            "shared_vpc_gateway_not_target": shared_vpc_gateway_not_target,
            "protected_interfaces": None,  # 未持久化于 operation → null（禁止编造）
        },
    }
