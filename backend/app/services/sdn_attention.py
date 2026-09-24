"""S2-016 VPC 可行动关注队列（attention）——纯函数/服务模块。

把 S2 已有的 scope 分类、scope exception、Leaf aggregate/diff、snapshot freshness
汇成一个保守、可解释、**只读**的 attention 投影，供 STRATA 展示「接下来值得处理什么」。
它不是根因分析、健康评分、修复计划或自动修复；不新增表/迁移/写接口/设备命令。

矩阵（保守，逐规则生成 item，可同设备多 item，key 不冲突）：
 1. scope=ambiguous                          → blocking   scope_uncertain          review_records
 2. targeted + aggregate=drifted             → blocking   confirmed_drift          inspect_differences
    （active exception 不消灭事实，仍 blocking 并携带 exception，不得降级成“无问题”）
 3. targeted + aggregate=stale/unknown/无 Leaf projection（或坏 aggregate，保守）
                                            → review     evidence_missing_or_stale refresh_evidence
 4. not_targeted/withdrawn + 无 active exception → review coverage_gap           review_coverage
    （只是覆盖缺口，不称故障）
 5. not_targeted/withdrawn + active exception  → deferred  coverage_deferred      review_exception
    （保留 scope 原分类）
 6. 任何 expired exception                   → review     exception_expired        refresh_evidence
    （例外结束先重新观察，不默认回填；与 blocking drift/scope_uncertain 可共存）
 7. 任何 invalid exception（或异常 exception 记录，保守）→ blocking exception_invalid repair_context_record
 8. targeted + aligned 且无 expired/invalid exception → 无 item；非 EVPN 不进入。

排序固定：blocking → review → deferred，再 device_id / category。
item key 稳定："{vpc_id}:{device_id}:{category}"。
坏字段稳定降级、绝不 500；source_refs 只含脱敏 ID/时间/状态引用。
"""
from typing import Optional

# ── 稳定语义字符串（语言中性，供前端 i18n）──
SEVERITY_BLOCKING = "blocking"
SEVERITY_REVIEW = "review"
SEVERITY_DEFERRED = "deferred"

CATEGORY_SCOPE_UNCERTAIN = "scope_uncertain"
CATEGORY_CONFIRMED_DRIFT = "confirmed_drift"
CATEGORY_EVIDENCE_MISSING_OR_STALE = "evidence_missing_or_stale"
CATEGORY_COVERAGE_GAP = "coverage_gap"
CATEGORY_COVERAGE_DEFERRED = "coverage_deferred"
CATEGORY_EXCEPTION_EXPIRED = "exception_expired"
CATEGORY_EXCEPTION_INVALID = "exception_invalid"

# 推荐动作（category → action）
CATEGORY_ACTION = {
    CATEGORY_SCOPE_UNCERTAIN: "review_records",
    CATEGORY_CONFIRMED_DRIFT: "inspect_differences",
    CATEGORY_EVIDENCE_MISSING_OR_STALE: "refresh_evidence",
    CATEGORY_COVERAGE_GAP: "review_coverage",
    CATEGORY_COVERAGE_DEFERRED: "review_exception",
    CATEGORY_EXCEPTION_EXPIRED: "refresh_evidence",
    CATEGORY_EXCEPTION_INVALID: "repair_context_record",
}

SEVERITY_ORDER = {SEVERITY_BLOCKING: 0, SEVERITY_REVIEW: 1, SEVERITY_DEFERRED: 2}

# 与 sdn_state_projection 的 scope/aggregate 语义保持一致（不重复造字符串）。
SCOPE_AMBIGUOUS = "ambiguous"
SCOPE_TARGETED = "targeted"
SCOPE_WITHDRAWN = "withdrawn"
SCOPE_NOT_TARGETED = "not_targeted"
AGG_DRIFTED = "drifted"
AGG_ALIGNED = "aligned"


def _safe_int(value) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _member_ref(member: dict) -> dict:
    """scope 成员脱敏引用（只含稳定字符串/计数）。"""
    return {
        "kind": "scope_member",
        "device_id": _safe_int(member.get("device_id")),
        "classification": member.get("classification"),
        "reason_code": member.get("reason_code") if isinstance(member.get("reason_code"), str) else None,
    }


def _leaf_ref(leaf: Optional[dict]) -> dict:
    """Leaf 脱敏引用（只含稳定 ID/状态）。"""
    out = {"kind": "leaf", "device_id": _safe_int((leaf or {}).get("device_id"))}
    if isinstance(leaf, dict) and leaf.get("aggregate") is not None:
        out["aggregate"] = leaf.get("aggregate")
    observed = (leaf or {}).get("observed") if isinstance(leaf, dict) else None
    if isinstance(observed, dict) and observed.get("snapshot_id") is not None:
        out["snapshot"] = {
            "kind": "snapshot",
            "snapshot_id": observed.get("snapshot_id"),
            "collected_at": observed.get("collected_at"),
            "stale": bool(observed.get("stale")),
        }
    return out


def _exception_ref(exc: dict) -> dict:
    """例外记录脱敏引用（不含 reason/任何业务文本之外的敏感字段）。"""
    return {
        "kind": "scope_exception",
        "vpc_id": _safe_int(exc.get("vpc_id")),
        "device_id": _safe_int(exc.get("device_id")),
        "exception_type": exc.get("exception_type"),
        "version": exc.get("version"),
        "updated_at": exc.get("updated_at"),
        "state": exc.get("state"),
    }


def _item(*, vpc_id: int, member: dict, category: str, severity: str, exception: Optional[dict], source_refs: list) -> dict:
    device_id = _safe_int(member.get("device_id"))
    return {
        "key": f"{vpc_id}:{device_id}:{category}",
        "vpc_id": vpc_id,
        "device_id": device_id,
        "name": member.get("name"),
        "host": member.get("host"),
        "severity": severity,
        "category": category,
        "reason_code": category,
        "recommended_action": CATEGORY_ACTION.get(category),
        "source_refs": source_refs,
        "exception": exception if isinstance(exception, dict) else None,
    }


def _items_for_member(*, vpc_id: int, member: dict, leaf: Optional[dict]) -> list:
    """单个 scope 成员（EVPN Leaf）的 attention items（矩阵逐条，可多条共存）。"""
    device_id = _safe_int(member.get("device_id"))
    if device_id is None:
        return []

    classification = member.get("classification")
    exc = member.get("exception") if isinstance(member.get("exception"), dict) else None
    exc_state = exc.get("state") if exc is not None else None
    aggregate = (leaf or {}).get("aggregate") if isinstance(leaf, dict) else None

    items: list[dict] = []

    # 例外类 item（与分类无关，先加，key 按 category 不冲突）
    if exc is not None:
        if exc_state == "expired":
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_EXCEPTION_EXPIRED,
                severity=SEVERITY_REVIEW, exception=exc, source_refs=[_exception_ref(exc)],
            ))
        elif exc_state != "active":
            # invalid / 缺失 / 畸形 state → 保守视为损坏记录
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_EXCEPTION_INVALID,
                severity=SEVERITY_BLOCKING, exception=exc, source_refs=[_exception_ref(exc)],
            ))

    # 分类类 item
    if classification == SCOPE_AMBIGUOUS:
        items.append(_item(
            vpc_id=vpc_id, member=member, category=CATEGORY_SCOPE_UNCERTAIN,
            severity=SEVERITY_BLOCKING, exception=exc,
            source_refs=[_member_ref(member)],
        ))
    elif classification == SCOPE_TARGETED:
        if aggregate == AGG_DRIFTED:
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_CONFIRMED_DRIFT,
                severity=SEVERITY_BLOCKING, exception=exc,
                source_refs=[_leaf_ref(leaf)],
            ))
        elif aggregate != AGG_ALIGNED:
            # stale/unknown/not_applicable/无 Leaf projection/坏 aggregate → 保守 review
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_EVIDENCE_MISSING_OR_STALE,
                severity=SEVERITY_REVIEW, exception=exc,
                source_refs=[_leaf_ref(leaf)],
            ))
        # aligned → 无 item（规则 8；除非已有 expired/invalid exception item）
    elif classification in (SCOPE_NOT_TARGETED, SCOPE_WITHDRAWN):
        if exc_state == "active":
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_COVERAGE_DEFERRED,
                severity=SEVERITY_DEFERRED, exception=exc,
                source_refs=[_member_ref(member)],
            ))
        else:
            items.append(_item(
                vpc_id=vpc_id, member=member, category=CATEGORY_COVERAGE_GAP,
                severity=SEVERITY_REVIEW, exception=exc,
                source_refs=[_member_ref(member)],
            ))
    # 其他/未知 classification → 无分类 item（坏字段稳定降级，例外 item 已单独处理）

    return items


def build_attention_items(*, vpc_id: int, members: list, leaves_by_device: Optional[dict] = None) -> list:
    """从已加载的 scope members + leaves（同一次 state-projection 数据）纯函数生成 items。

    members: scope.members 列表（每个含 device_id/name/host/classification/reason_code/
             exception[S2-014 白名单或 None]，均由 endpoint 批量加载，无 N+1）。
    leaves_by_device: 已加载 leaves 按 device_id 索引；缺失成员视为无 Leaf projection。
    """
    if not isinstance(members, list):
        return []
    leaves_by_device = leaves_by_device if isinstance(leaves_by_device, dict) else {}

    items: list[dict] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        leaf = leaves_by_device.get(_safe_int(member.get("device_id")))
        items.extend(_items_for_member(vpc_id=vpc_id, member=member, leaf=leaf))

    items.sort(key=lambda i: (
        SEVERITY_ORDER.get(i["severity"], 99),
        i["device_id"] if i["device_id"] is not None else 0,
        i["category"],
    ))
    return items


def attention_projection(*, vpc_id: int, members: list, leaves_by_device: Optional[dict] = None) -> dict:
    """顶层 additive attention 投影：{"summary": {...}, "items": [...]}。"""
    items = build_attention_items(vpc_id=vpc_id, members=members, leaves_by_device=leaves_by_device)
    summary = {
        "total": len(items),
        "blocking": sum(1 for i in items if i["severity"] == SEVERITY_BLOCKING),
        "review": sum(1 for i in items if i["severity"] == SEVERITY_REVIEW),
        "deferred": sum(1 for i in items if i["severity"] == SEVERITY_DEFERRED),
    }
    return {"summary": summary, "items": items}
