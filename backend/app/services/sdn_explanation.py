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
