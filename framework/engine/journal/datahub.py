#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""datahub.py — 持仓数据仓只读索引（纯标准库，零第三方依赖）

存在理由：A-06（孤儿标的）与 A-11（引用必须真实存在）都要求校验层能回答
「这个代码在不在数据仓里」「这个字段在不在数据仓里」。没有这一层索引，
这两个断言只能靠猜——而一个靠猜的孤儿检测等于没有检测。

单一事实源：config/portfolio.yaml（ADR-007 U6）。本模块**不缓存**配置内容，
每次构造索引都从传入的 dict 建，缓存由调用方负责。持有过期索引比不缓存更危险：
校验器会拿旧持仓判定「可平仓」，而实际仓位已经变了。

代码键：同时按原样代码与规范化代码建键。原因是基金代码 000979 经
normalize_code 会变成 sz000979（它其实是场外基金，不是深市标的），
只存规范化键会让全部场外基金查不到、从而让 A-06 对基金轨整体失效。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 相对定位注入（journal -> framework/scripts），不写死绝对路径。
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import paths  # noqa: E402  A-04：路径统一由 paths.py 导出
from codes import normalize_code  # noqa: E402  A-10：前缀推断单一实现
from yaml_min import (  # noqa: E402
    ConfigError, parse_yaml_subset, parse_yaml_subset_indexed,
)

# 场外基金在数据仓里的规模口径字段（不是份额）
FUND_FIELDS = ("amount", "holding_period_days", "plan", "listing", "name")
STOCK_FIELDS = ("shares", "available", "cost", "listing", "name")
GRID_FIELDS = ("base_price", "range_low", "range_high", "step_pct",
               "per_trade", "min_position", "max_position", "enabled")


class PortfolioIndex:
    """持仓数据仓的只读视图。

    records[code] -> {"track","listing","fields":set,"values":dict,"grid":dict}
    值全部来自配置文件，不在此层补任何默认值：available 缺失时回落到 shares
    是引擎既有契约（validate_config.build_export 同款），但回落结果记在
    values["available"] 里，A-05 判定时看到的是**实际用于判定的值**，
    而不是配置里的原值——两者不一致本身就是需要暴露的问题。
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg or {}
        hold = (self.cfg.get("holdings") or {})
        self.records: dict = {}
        self._grid_by_code: dict = {}
        self._index_stock(hold.get("stock") or {})
        self._index_fund(hold.get("fund") or {})
        self._index_gold(hold.get("gold") or [])

    def _index_stock(self, stock: dict) -> None:
        for g in stock.get("grid") or []:
            if isinstance(g, dict) and g.get("code"):
                # 两种键都存：grid 段读时用 normalize_code，持仓段建索引时
                # 用原样代码。只存一种会让另一半永远查不到网格参数——
                # 症状是 A-04 误报「缺 base_price」，而配置里明明写了。
                for key in self._keys(g.get("code")):
                    self._grid_by_code.setdefault(key, g)
        for p in stock.get("positions") or []:
            if not isinstance(p, dict) or not p.get("code"):
                continue
            values = {k: p.get(k) for k in STOCK_FIELDS}
            values["available"] = p.get("available", p.get("shares"))
            values["shares"] = p.get("shares")
            values["code"] = str(p.get("code"))
            grid = (self._grid_by_code.get(normalize_code(p.get("code")))
                    or self._grid_by_code.get(str(p.get("code")).strip()) or {})
            gvals = {k: grid.get(k) for k in GRID_FIELDS if k in grid}
            self._add(values, "stock", grid=gvals)

    def _index_fund(self, fund: dict) -> None:
        for p in fund.get("positions") or []:
            if not isinstance(p, dict) or not p.get("code"):
                continue
            values = {k: p.get(k) for k in FUND_FIELDS}
            values["code"] = str(p.get("code"))
            self._add(values, "fund")

    def _index_gold(self, gold: list) -> None:
        for g in gold or []:
            if not isinstance(g, dict) or not g.get("name"):
                continue
            key = f"gold:{g.get('name')}"
            self.records[key] = {
                "track": "gold", "listing": None, "grid": {},
                "fields": {"name", "amount"},
                "values": {"name": g.get("name"), "amount": g.get("amount"),
                           "code": key},
            }

    def _add(self, values: dict, track: str, grid: dict | None = None) -> None:
        listing = values.get("listing")
        if listing is None:
            # 不猜归属：listing 缺失时留 None，让 A-06/A-15 去报错。
            # 在此按 track 反推 listing 等于把「配置漏填」变成「静默合法」。
            listing = "exchange" if track == "stock" else "otc"
        rec = {"track": track, "listing": listing, "grid": grid or {},
               "fields": set(values) - {"code"}, "values": values}
        for key in self._keys(values.get("code")):
            self.records.setdefault(key, rec)

    @staticmethod
    def _keys(raw) -> tuple:
        """一只标的的全部可查键：原样代码 + 规范化代码。"""
        s = str(raw).strip()
        norm = normalize_code(raw)
        return (s, norm) if norm != s else (s,)

    # -- 查询 ---------------------------------------------------------------
    def get(self, code):
        """按代码取持仓记录，查不到返回 None（A-06 的唯一判据）。"""
        if code is None:
            return None
        s = str(code).strip()
        return self.records.get(s) or self.records.get(normalize_code(code))

    def has(self, code) -> bool:
        return self.get(code) is not None

    def listing_of(self, code):
        rec = self.get(code)
        return rec.get("listing") if rec else None

    def available_of(self, code):
        """当前可平仓量。查不到标的返回 None——调用方必须自行处理未知，
        不在此返回 0：0 会让 A-05 变成「静默判为不可平仓」。"""
        rec = self.get(code)
        return None if not rec else rec["values"].get("available")

    def has_field(self, code, field) -> bool:
        """A-11 用：字段是否真实存在于数据仓。"""
        rec = self.get(code)
        return bool(rec) and (field in rec["fields"] or field in rec["grid"])

    def value(self, code, field):
        rec = self.get(code)
        if not rec:
            return None
        if field in rec["grid"]:
            return rec["grid"].get(field)
        return rec["values"].get(field)

    def codes(self) -> list:
        """数据仓内全部可查键（去重后按插入序）。"""
        return list(self.records)

    def track_codes(self, track: str) -> list:
        """按轨道取代码列表。取的是 values["code"] 原值，不是索引键——
        索引键含规范化形式，回传给用户会造成「sz000979」这种不存在的东西。"""
        out = []
        for rec in self.records.values():
            if rec["track"] == track and rec["values"]["code"] not in out:
                out.append(rec["values"]["code"])
        return out

    def risk_param(self, key):
        return (self.cfg.get("risk") or {}).get(key)

    def cash_amount(self):
        return (self.cfg.get("cash") or {}).get("amount")


def build_index(cfg: dict) -> PortfolioIndex:
    return PortfolioIndex(cfg)


def load_index(path=None) -> PortfolioIndex:
    """从 portfolio.yaml 读配置并建索引。路径默认走 paths.PORTFOLIO，
    支持 PULSE_CONFIG 环境变量覆盖——不新增第二份路径定义。"""
    target = Path(path).expanduser() if path else paths.PORTFOLIO
    if not target.is_file():
        raise FileNotFoundError(f"持仓数据仓不存在: {target}")
    try:
        cfg, _ = parse_yaml_subset_indexed(target.read_text(encoding="utf-8"))
    except ConfigError as err:
        raise ConfigError(f"持仓数据仓解析失败: {err}") from err
    return PortfolioIndex(cfg)


__all__ = ["PortfolioIndex", "build_index", "load_index", "parse_yaml_subset",
           "FUND_FIELDS", "STOCK_FIELDS", "GRID_FIELDS"]