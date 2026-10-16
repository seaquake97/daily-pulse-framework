#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_data.json 硬校验器 — daily-decision-engine 步骤3
任一断言失败 → rating=暂停，输出缺口清单。LLM 无权跳过。

用法:
    python3 validate_market_data.py <market_data.json> [--expect-date YYYY-MM-DD]

退出码: 0=全部通过, 1=存在失败断言, 2=文件/格式错误
"""
import json
import sys
import argparse
from datetime import date, datetime


def fail(errors, msg):
    errors.append(msg)
    print(f"  ❌ {msg}")


def warn(msg):
    print(f"  ⚠️ {msg}（降级处理，不计入失败）")


def ok(msg):
    print(f"  ✅ {msg}")


def num(v):
    """安全转 float，失败返回 None。"""
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def validate(data, expect_date=None, errors=None):
    if errors is None:
        errors = []

    print("[1] 结构与日期校验")
    if not isinstance(data, dict):
        fail(errors, "market_data.json 顶层必须是对象")
        return errors
    ok("顶层结构为对象")

    d_date = data.get("date")
    if not d_date:
        fail(errors, "缺少 date 字段")
    else:
        if expect_date and str(d_date) != expect_date:
            fail(errors, f"date={d_date} 与期望交易日 {expect_date} 不一致（疑似陈旧/写死数据）")
        else:
            ok(f"date={d_date}")

    print("[2] 指数行情断言（time==date 且 amount>0，|chg|<=10%）")
    idx = data.get("indices") or {}
    required_idx = ["sh000001", "sz399001", "sz399006", "sh000300", "sh000688", "bj899050"]
    for code in required_idx:
        item = idx.get(code)
        if not isinstance(item, dict):
            fail(errors, f"指数 {code} 缺失")
            continue
        t = item.get("time")
        price = num(item.get("price"))
        chg = num(item.get("change_percent"))
        amount = num(item.get("amount"))
        if t is None:
            fail(errors, f"指数 {code} 缺少 time 字段")
        elif expect_date and str(t) != expect_date:
            fail(errors, f"指数 {code}.time={t} != {expect_date}（非当日实时数据）")
        if price is None or price <= 0:
            fail(errors, f"指数 {code} price 无效: {item.get('price')}")
        if amount is None or amount <= 0:
            fail(errors, f"指数 {code} amount 无效: {item.get('amount')}")
        if chg is None:
            fail(errors, f"指数 {code} change_percent 缺失")
        elif abs(chg) > 10:
            fail(errors, f"指数 {code} 单日涨跌幅 {chg}% 超出 ±10% 合理区间（异常值）")
    if not any("指数" in e for e in errors):
        ok(f"{len(required_idx)} 个指数 time/price/amount/涨跌幅全部有效")

    print("[3] 成交额交叉验证（指数成交额之和 vs changedist.totalAmount，偏差<2%）")
    total_yi = num(data.get("total_amount_yi"))
    if total_yi is None or total_yi <= 0:
        fail(errors, "total_amount_yi 缺失或无效")
    else:
        ok(f"total_amount_yi={total_yi:,.2f} 亿")
    mb = data.get("market_breadth") or {}
    cd_total = num(mb.get("total_amount"))
    if cd_total:
        cd_yi = cd_total / 1e8
        if total_yi:
            dev = abs(cd_yi - total_yi) / total_yi * 100
            if dev >= 2:
                fail(errors, f"成交额偏差 {dev:.2f}% >= 2%（指数和 {total_yi:,.0f} 亿 vs 涨跌分布 {cd_yi:,.0f} 亿）")
            else:
                ok(f"交叉验证通过（偏差 {dev:.2f}%）")
    else:
        print("  ⚠️ changedist.totalAmount 缺失，跳过交叉验证（标注数据缺口）")

    print("[4] 市场宽度合理性（涨+跌+平 ∈ [4800,5600]）")
    up, down, flat = num(mb.get("up")), num(mb.get("down")), num(mb.get("flat"))
    if None in (up, down, flat):
        fail(errors, "market_breadth.up/down/flat 缺失")
    else:
        total = up + down + flat
        if not (4800 <= total <= 5600):
            fail(errors, f"涨跌平家数合计 {total} 不在 [4800,5600] 合理区间")
        else:
            ok(f"涨跌平合计 {total} 家（涨{int(up)}/跌{int(down)}/平{int(flat)}）")
        lu, ld = num(mb.get("limit_up")), num(mb.get("limit_down"))
        if lu is None or ld is None:
            fail(errors, "market_breadth.limit_up/limit_down 缺失")
        else:
            ok(f"涨停 {int(lu)} / 跌停 {int(ld)}")

    print("[5] 持仓行情完整性（price>0）")
    holdings = data.get("holdings") or {}
    if not holdings:
        # v1.3 终验修复：持仓解析失败按降级链走"仅大盘研判"，记警告而非失败
        # （原为 fail，与 SKILL.md 降级链"持仓解析失败→仅大盘研判"自相矛盾）
        warn("holdings 为空 → 任务降级为「仅大盘研判，不含持仓诊断」")
    else:
        bad = [c for c, h in holdings.items()
               if not isinstance(h, dict) or num(h.get("price")) is None or num(h.get("price")) <= 0]
        if bad:
            fail(errors, f"持仓行情无效: {bad}")
        else:
            ok(f"{len(holdings)} 只持仓行情全部有效")

    print("[6] 占位符/写死痕迹扫描")
    raw = json.dumps(data, ensure_ascii=False)
    for pat in ["TODO", "XXX", "待填", "placeholder", "0.00%"]:
        if pat in raw:
            fail(errors, f"发现占位符痕迹: {pat}")
    if "verdict" not in data:
        fail(errors, "缺少 verdict 字段（compute_signals.py 未执行，评级不得由 LLM 主观给出）")
    else:
        v = data["verdict"]
        print(f"  ✅ verdict 存在: rating={v.get('rating')}, sigma={v.get('sigma')}")

    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--expect-date", default=None, help="期望交易日 YYYY-MM-DD，缺省用文件 date")
    args = ap.parse_args()

    try:
        with open(args.path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 文件不存在: {args.path}")
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        sys.exit(2)

    print(f"=== market_data.json 硬校验: {args.path} ===")
    errors = validate(data, args.expect_date)
    print()
    if errors:
        print(f"🚫 校验未通过，共 {len(errors)} 项失败 → rating=暂停，输出缺口清单：")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    print("🎉 全部硬断言通过，允许进入研判阶段。")
    sys.exit(0)


if __name__ == "__main__":
    main()
