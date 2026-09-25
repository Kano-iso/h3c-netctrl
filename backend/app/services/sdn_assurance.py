"""S3-001 VPC 受限保障评估（只读、确定性建议，NEXT/S3 后端切片）。

评估完全复用 S2 已持久化的 state projection / attention 事实，不重新推断设备事实、
不采集设备、不下发配置、不自动修复、不做后台调度。输出 overall
（healthy / attention / blocked / insufficient_evidence）与逐项白名单建议；建议码为
确定性动作（review_scope / refresh_evidence / inspect_drift / resolve_ambiguity /
repair_context / review_exception），绝不含设备命令、自动修复计划或“根因已确认”暗示。

边界语义（与 S2-016 attention 契约一致，本模块不做新推断）：
- active maintenance exception 可把 coverage gap 保持 deferred（不升级为 blocking），
  但绝不吞掉 confirmed_drift blocking 事实；
- policy disabled 不改变评估结果，只由调用方在 run 上记录 policy_enabled=false。
"""
import json
from datetime import datetime
from typing import Optional

OVERALL_HEALTHY = "healthy"
OVERALL_ATTENTION = "attention"
OVERALL_BLOCKED = "blocked"
OVERALL_INSUFFICIENT = "insufficient_evidence"

ASSURANCE_CADENCES = ("manual", "10m", "30m", "1h")
ASSURANCE_RESPONSE_MODE = "observe_only"
ASSURANCE_TRIGGERS = ("manual", "scheduled", "event")

# 类别 → 确定性建议码（保证层建议，与 attention 的 recommended_action 平行但独立）。
RECOMMENDATION_BY_CATEGORY = {
    "coverage_gap": "review_scope",
    "evidence_missing_or_stale": "refresh_evidence",
    "confirmed_drift": "inspect_drift",
    "scope_uncertain": "resolve_ambiguity",
    "exception_expired": "refresh_evidence",
    "exception_invalid": "repair_context",
    "coverage_deferred": "review_exception",
}

SEVERITY_WEIGHT = {"blocking": 0, "review": 1, "deferred": 2}

# 项字段白名单：与 attention 项一致（source_refs/exception 已是脱敏引用），
# 任何原始配置/CLI/凭据/error 字段都会被丢弃。
_ITEM_FIELDS = (
    "key", "vpc_id", "device_id", "name", "host",
    "severity", "category", "source_refs", "exception",
)


def assurance_item(item: dict) -> Optional[dict]:
    """把 attention 项收敛为保障项（白名单字段 + 确定性建议码）；畸形输入 → None。"""
    if not isinstance(item, dict):
        return None
    recommendation = RECOMMENDATION_BY_CATEGORY.get(item.get("category"))
    if recommendation is None:
        return None
    out = {f: item.get(f) for f in _ITEM_FIELDS}
    out["source_refs"] = _source_refs(item.get("source_refs"))
    out["exception"] = _exception(item.get("exception"))
    out["recommendation"] = recommendation
    return out


def _source_refs(value) -> list:
    """只保留 S2 attention 契约中的脱敏引用字段。"""
    if not isinstance(value, list):
        return []
    allowed = {
        "kind", "device_id", "classification", "reason_code", "aggregate",
        "snapshot_id", "collected_at", "stale", "vpc_id", "exception_type",
        "version", "updated_at", "state",
    }
    refs = []
    for ref in value:
        if not isinstance(ref, dict):
            continue
        clean = {key: ref.get(key) for key in allowed if key in ref}
        snapshot = ref.get("snapshot")
        if isinstance(snapshot, dict):
            clean["snapshot"] = {
                key: snapshot.get(key)
                for key in ("kind", "snapshot_id", "collected_at", "stale")
                if key in snapshot
            }
        refs.append(clean)
    return refs


def _exception(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    allowed = (
        "vpc_id", "device_id", "exception_type", "reason", "expires_at",
        "state", "version", "created_at", "updated_at",
    )
    return {key: value.get(key) for key in allowed if key in value}


def _facts_snapshot(projection: dict) -> dict:
    """评估所基于的持久化事实（白名单快照：scope 摘要 + 逐 Leaf aggregate/观测引用 +
    attention 摘要；不含原始配置/CLI/凭据/error）。"""
    if not isinstance(projection, dict):
        return {"vpc_version": None, "scope": {}, "leaves": [], "attention": {}}
    scope = projection.get("scope") or {}
    leaves = []
    for leaf in projection.get("leaves") or []:
        if not isinstance(leaf, dict):
            continue
        observed = leaf.get("observed")
        observed = observed if isinstance(observed, dict) else {}
        leaves.append({
            "device_id": leaf.get("device_id"),
            "name": leaf.get("name"),
            "aggregate": leaf.get("aggregate"),
            "snapshot_id": observed.get("snapshot_id"),
            "collected_at": observed.get("collected_at"),
        })
    attention = projection.get("attention") or {}
    attention_summary = attention.get("summary") if isinstance(attention, dict) else None
    return {
        "vpc_version": (projection.get("vpc") or {}).get("version"),
        "scope": (scope.get("summary") or {}) if isinstance(scope, dict) else {},
        "leaves": leaves,
        "attention": {
            "total": (attention_summary or {}).get("total"),
            "blocking": (attention_summary or {}).get("blocking"),
            "review": (attention_summary or {}).get("review"),
            "deferred": (attention_summary or {}).get("deferred"),
        },
    }


def evaluate_assurance(projection: dict, *, now: Optional[datetime] = None) -> dict:
    """对同一份 state projection 载荷做只读评估（纯函数，零 DB 写、零设备 I/O）。"""
    now = now or datetime.utcnow()
    items: list[dict] = []
    if isinstance(projection, dict):
        attention = projection.get("attention")
        raw_items = attention.get("items") if isinstance(attention, dict) else None
        for item in raw_items or []:
            converted = assurance_item(item)
            if converted is not None:
                items.append(converted)
    # 与 attention 固定排序一致：blocking → review → deferred，再 device_id/category。
    items.sort(
        key=lambda i: (
            SEVERITY_WEIGHT.get(i.get("severity"), 9),
            i.get("device_id") or 0,
            i.get("category") or "",
        )
    )

    blocking = sum(1 for i in items if i.get("severity") == "blocking")
    review = sum(1 for i in items if i.get("severity") == "review")
    deferred = sum(1 for i in items if i.get("severity") == "deferred")

    scope = projection.get("scope") if isinstance(projection, dict) else None
    scope_summary = scope.get("summary") if isinstance(scope, dict) else None
    eligible = int((scope_summary or {}).get("eligible") or 0)

    if blocking:
        overall = OVERALL_BLOCKED
    elif eligible == 0:
        # 无任何可评估对象（fabric 无 EVPN Leaf）→ 证据不足，不能断言 healthy。
        overall = OVERALL_INSUFFICIENT
    elif items and all(i.get("category") == "evidence_missing_or_stale" for i in items):
        # 有评估对象但全部证据缺失/陈旧，同样不能把未知状态包装成普通提醒。
        overall = OVERALL_INSUFFICIENT
    elif items:
        overall = OVERALL_ATTENTION
    else:
        overall = OVERALL_HEALTHY

    return {
        "overall": overall,
        "summary": {
            "overall": overall,
            "total": len(items),
            "blocking": blocking,
            "review": review,
            "deferred": deferred,
        },
        "items": items,
        "facts": _facts_snapshot(projection),
    }


def _json_default(obj):
    """白名单 JSON 序列化兜底：datetime → ISO 字符串；其余非可序列化值 → None（绝不放行原始对象）。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return None


def run_summary_json(result: dict) -> str:
    """持久化用 summary JSON（含 overall；畸形输入稳定降级）。"""
    if not isinstance(result, dict):
        return json.dumps({"overall": OVERALL_INSUFFICIENT, "total": 0, "blocking": 0, "review": 0, "deferred": 0}, ensure_ascii=False)
    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {"overall": result.get("overall", OVERALL_INSUFFICIENT), "total": 0, "blocking": 0, "review": 0, "deferred": 0}
    return json.dumps(summary, ensure_ascii=False, default=_json_default)


def items_json(items: list) -> str:
    return json.dumps([i for i in items if isinstance(i, dict)], ensure_ascii=False, default=_json_default)


def facts_json(result: dict) -> str:
    facts = result.get("facts")
    if not isinstance(facts, dict):
        facts = {"vpc_version": None, "scope": {}, "leaves": [], "attention": {}}
    return json.dumps(facts, ensure_ascii=False, default=_json_default)
