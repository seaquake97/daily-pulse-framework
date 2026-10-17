#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contracts.py — 决策日志契约常量：枚举、错误码、键集（纯标准库，零依赖）

依赖图的叶子：不 import 本包任何其他模块，也不 import framework/scripts 下的模块。
枚举与键集集中在此，是为了让校验器、四分类层、测试三方引用同一份清单——
三处各写一份清单，迟早漂移，届时「校验通过」与「测试通过」指向不同契约。

命名注意：本文件**不得**叫 codes.py。framework/scripts/codes.py 是全框架唯一的
市场前缀推断实现，而本包会把 journal 目录插进 sys.path[0]；同名模块会让
`from codes import normalize_code` 在 rules_stock 里解析到本文件，静默换掉实现。
这是真实的坑，不是洁癖。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 契约版本
# ---------------------------------------------------------------------------
JOURNAL_VERSION = 1

# ---------------------------------------------------------------------------
# 观察点可观测性（ADR-007 派生：明确建议的质量由字段完整性保证）
# ---------------------------------------------------------------------------
OBSERVABLE_CLASS = ("EXACT", "QUANTIFIED", "UNFALSIFIABLE", "UNOBSERVABLE")
FALSIFIABILITY = ("FALSIFIABLE", "PARTIAL", "UNFALSIFIABLE")

# 观察点类型：四分类层的判据维度。显式枚举而非关键词嗅探——
# 嗅探「这段话里有没有『突破』」会在改写文案后静默失效，且错判不报错。
POINT_CLASS = ("PRICE", "NAV", "POSITION", "GRID", "NEWS")
POINT_CLASS_LABEL = {
    "PRICE": "价格类（分时价/突破位）",
    "NAV": "净值类（场外基金日频净值）",
    "POSITION": "仓位类（持仓比例/可用量）",
    "GRID": "网格类（挂单/条件单）",
    "NEWS": "消息面类",
}

# ---------------------------------------------------------------------------
# 动作与轨道（ADR-007 §2.2：双轨隔离的判据是 listing，由数据决定）
# ---------------------------------------------------------------------------
TRACK = ("stock", "fund", "news")
LISTING_EXCHANGE = "exchange"
LISTING_OTC = "otc"

ACTION_KIND = ("buy", "sell", "grid", "full_rebalance", "adjust_plan", "hold")
# 场外基金只有这三种动作（ADR-007 §2.2：无挂单即无中间态）
FUND_ACTION_KIND = ("buy", "sell", "adjust_plan")
# 出场类：需要证明当前可平仓（A-05）
EXIT_KIND = ("sell",)
# 网格类：需要 base_price（A-04）
GRID_KIND = ("grid",)
# 同一 observation_point 下互斥的类内动作对（A-08）。成对给出而非单值：
# 互斥是二元关系，写成单值就只能在调用侧硬编码另一半。
EXCLUSIVE_PAIRS = (("grid", "full_rebalance"),)

AMOUNT_UNIT = ("money", "shares")
REQUESTED_POSITION_MODE = ("buy", "sell", "hold", "add", "reduce")

# ---------------------------------------------------------------------------
# 风险与研判可信度
# ---------------------------------------------------------------------------
METHOD_SEMANTICS = ("entry_gate", "hard_cap", "both")
RISK_TIER = ("low", "medium", "high", "severe")
CLASSIFICATION_VERIFIED = ("SEMANTIC_VERIFIED", "DERIVED", "UNVERIFIED",
                           "SEMANTIC_UNCALIBRATED")
PRECISION_SOURCE = ("EXTERNAL_PRIMARY", "EXTERNAL_SECONDARY", "DERIVED",
                    "MODEL_INTUITION", "OPEN", "SEMANTIC_UNCALIBRATED")
# GENERATED 被移出合法集：A-10 硬拒。留着名字是为了让错误消息能点名它。
REASONING_BASIS = ("OPEN", "MODEL_INTUITION")
REASONING_BASIS_FORBIDDEN = "GENERATED"
RESOLUTION_STATUS = ("OPEN", "HIT", "RESOLVED", "EXPIRED")

# ---------------------------------------------------------------------------
# 四分类（不触发类判定）
# ---------------------------------------------------------------------------
CLASS_ACTIONABLE = "actionable"
CLASS_WATCH_ONLY = "watch_only"
CLASS_MONITORING_ONLY = "monitoring_only"
CLASS_FORBIDDEN = "forbidden"
CLASSIFICATIONS = (CLASS_ACTIONABLE, CLASS_WATCH_ONLY,
                   CLASS_MONITORING_ONLY, CLASS_FORBIDDEN)
# 输出 actionable 时这三个键必须齐备（§3 契约）
ACTIONABLE_REQUIRED = ("action", "gates_passed", "risk")

# 场外基金无分时价，价格类观察点在此降级并换代理指标（§3）
PROXY_INDICATOR = "重仓股实时涨跌"
PROXY_FLAG = "PROXY_SUBSTITUTED"
# 代理性质的标注文本。必须写明「代理」二字：只写指标名会让读者以为
# 那是场外基金自己的实时数据，而它其实是成分股的行情。
PROXY_BASIS_NOTE = f"{PROXY_INDICATOR}（代理指标，非场外分时价）"

# ---------------------------------------------------------------------------
# 阈值降级哨兵（A-09）：这些值是「拿不到真值」的占位，不是测量结果
# ---------------------------------------------------------------------------
DEGRADED_SENTINELS = (0, 0.0, "阈值带", "阈值", "TBD", "N/A")

# ---------------------------------------------------------------------------
# 键集：封闭集合校验用。出现未知键即硬错误（拼错必须炸，不能静默生效）
# ---------------------------------------------------------------------------
OBS_KEYS = ("code", "trigger", "condition", "invalidation", "monitoring_window",
            "observable_class", "falsifiability", "point_class", "threshold",
            "proxy", "proxy_basis", "note", "degraded", "degraded_reason")
# A-02：这四个字段任一缺失即拒
OBS_MANDATORY = ("trigger", "condition", "invalidation", "monitoring_window")

REQUESTED_POSITION_KEYS = ("instrument_code", "amount", "amount_unit",
                           "basis", "converted_amount")
ACTION_KEYS = ("code", "track", "instrument_code", "amount", "amount_unit",
               "converted_amount", "price", "priority", "trigger",
               "invalidation", "base_price", "kind", "degraded",
               "degraded_reason")
RISK_KEYS = ("tier", "max_trade_loss", "thesis_invalidation", "method_semantics",
             "exception_owner", "declared_exception", "stop_loss",
             "confidence", "limit_conditions")
# A-07：这四个字段任一缺失即拒
RISK_MANDATORY = ("stop_loss", "method_semantics", "confidence", "limit_conditions")

CHAIN_KEYS = ("code", "condition", "action_if_hit", "resolution_status")
DERIVATION_KEYS = ("step", "input_ref", "output_ref")
BLOCKED_KEYS = ("action_code", "gate_id", "blocking_value", "blocking_domain")
ENTRY_KEYS = ("observation_point", "action", "risk", "invalidation_chain",
              "classification_verified", "precision_source", "as_of",
              "verified_by", "reasoning_basis", "derivation",
              "gate_blocked_actions", "gates_passed", "missing",
              "covers_paths", "requested_position", "version")
# 禁止出现在 derivation 里的键：它会让引用变成「按格式书写」而非「按事实存在」
DERIVATION_FORBIDDEN = ("reference_format", "format", "template", "schema_ref")

# ---------------------------------------------------------------------------
# 错误码：给 CI 断言与外部脚本一个稳定抓手。只加不改、只扩不改义。
# ---------------------------------------------------------------------------
E_STRUCTURE = "E_J_STRUCTURE"
E_REQUIRED = "E_J_REQUIRED"
E_TYPE = "E_J_TYPE"
E_ENUM = "E_J_ENUM"
E_UNKNOWN_KEY = "E_J_UNKNOWN_KEY"

E_A01_REQUESTED_POSITION = "E_A01_REQUESTED_POSITION"
E_A02_OBSERVATION_FIELDS = "E_A02_OBSERVATION_FIELDS"
E_A03_AMOUNT_UNIT = "E_A03_AMOUNT_UNIT"
E_A04_GRID_BASE_PRICE = "E_A04_GRID_BASE_PRICE"
E_A05_EXIT_AVAILABLE = "E_A05_EXIT_AVAILABLE"
E_A06_ORPHAN_INSTRUMENT = "E_A06_ORPHAN_INSTRUMENT"
E_A07_RISK_FIELDS = "E_A07_RISK_FIELDS"
E_A08_GRID_REBALANCE_EXCLUSIVE = "E_A08_GRID_REBALANCE_EXCLUSIVE"
E_A09_DEGRADED_MARKING = "E_A09_DEGRADED_MARKING"
E_A10_REASONING_BASIS = "E_A10_REASONING_BASIS"
E_A11_DERIVATION_REF = "E_A11_DERIVATION_REF"
E_A12_MISSING_MUST_BE_NULL = "E_A12_MISSING_MUST_BE_NULL"
E_A13_ACTION_COUNT_CAP = "E_A13_ACTION_COUNT_CAP"
E_A14_UNVERIFIED_WITH_ACTION = "E_A14_UNVERIFIED_WITH_ACTION"
E_A15_TRACK_INDEPENDENCE = "E_A15_TRACK_INDEPENDENCE"
E_A16_COVERS_PATHS = "E_A16_COVERS_PATHS"

# 16 条断言 → 错误码，供测试与 CI 断言做一一映射校验
ASSERTION_CODES = (
    E_A01_REQUESTED_POSITION, E_A02_OBSERVATION_FIELDS, E_A03_AMOUNT_UNIT,
    E_A04_GRID_BASE_PRICE, E_A05_EXIT_AVAILABLE, E_A06_ORPHAN_INSTRUMENT,
    E_A07_RISK_FIELDS, E_A08_GRID_REBALANCE_EXCLUSIVE, E_A09_DEGRADED_MARKING,
    E_A10_REASONING_BASIS, E_A11_DERIVATION_REF, E_A12_MISSING_MUST_BE_NULL,
    E_A13_ACTION_COUNT_CAP, E_A14_UNVERIFIED_WITH_ACTION,
    E_A15_TRACK_INDEPENDENCE, E_A16_COVERS_PATHS,
)

# A-13 门禁上限：同一 observation_point 的动作数上限（可配置，默认 3）
DEFAULT_MAX_ACTIONS_PER_OBSERVATION = 3