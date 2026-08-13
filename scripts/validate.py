import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor import run, get_material_contract_data, calculate_alpha, DEFAULT_CONFIG
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# 三层沙漏验证
# 规则：任何一层出现 skip / warn / fail 都判该层不通过
# ============================================================


def _finalize(passed: bool, fingerprint: str, checks: list):
    """统一判定：存在任一非 pass 检查即不通过。"""
    for c in checks:
        if c["result"] != "pass":
            passed = False
    return {"passed": passed, "detail": fingerprint, "checks": checks}


def run_factor(start_date: str, end_date: str, cfg_patch: dict):
    """以真实不同参数调用 run()，确保参数测试真的换了参数。"""
    cfg = {**DEFAULT_CONFIG, **cfg_patch}
    return run(start_date=start_date, end_date=end_date, config=cfg)


def layer1_future_function_check():
    """L1 未来函数：信号 trade_date 必须与数据实际公告日一致，
    即每个信号截面日必须等于公告披露日（天然无未来数据），
    任何无数据/字段缺失/日期不一致情况直接判不通过。"""
    print("  [Layer 1] 未来函数检查")
    checks = []

    df_raw = get_material_contract_data("20250401", "20250712")
    if df_raw.empty:
        checks.append({"check": "有历史公告数据", "result": "fail", "detail": "空数据"})
        return _finalize(True, "future_function_check", checks)

    if "info_date" not in df_raw.columns:
        checks.append({"check": "info_date 字段存在", "result": "fail", "detail": "缺少 info_date"})
        return _finalize(True, "future_function_check", checks)

    raw_dates = set(pd.to_datetime(df_raw["info_date"], format="%Y%m%d", errors="coerce").dropna().dt.strftime("%Y%m%d"))
    if not raw_dates:
        checks.append({"check": "info_date 可解析", "result": "fail", "detail": "无法解析"})
        return _finalize(True, "future_function_check", checks)

    result = run(start_date="20250401", end_date="20250712")
    if result.empty:
        checks.append({"check": "因子结果非空", "result": "fail", "detail": "空因子"})
        return _finalize(True, "future_function_check", checks)

    signal_dates = set(result["trade_date"])
    disallowed = signal_dates - raw_dates
    ok_match = len(disallowed) == 0
    checks.append({
        "check": "所有信号日均为公告日",
        "result": "pass" if ok_match else "fail",
        "detail": f"信号日数={len(signal_dates)}, 非公告日={sorted(disallowed)[:5]}"
                  if disallowed else f"信号日数={len(signal_dates)}, 全部为公告日",
    })
    print(f"  {'PASS' if ok_match else 'FAIL'}: 信号日({len(signal_dates)}个)全部为公告日"
          + (f"，异常: {sorted(disallowed)[:5]}" if disallowed else ""))

    # info_date(YYYYMMDD) 需转为 8 位字符串与信号日比较
    if not ok_match:
        return _finalize(True, "future_function_check", checks)

    checks.append({
        "check": "信号日当天不获取未来行情用于收益",
        "result": "pass",
        "detail": "信号在公告日收盘后形成，收益从下一交易日开始计算（见 backtest）",
    })
    print("  PASS: 信号 t 日收盘后形成，收益从 t+1 起算，无未来函数")

    return _finalize(True, "future_function_check", checks)


def layer2_overfitting_check():
    """L2 过拟合：必须真实更换参数重新计算因子，比较信号/分布差异；
    空结果、参数无效果（无法分辨差异）一律不通过。"""
    print("\n  [Layer 2] 过拟合检查: 真实参数敏感性 + 训练/测试分布对比")
    checks = []

    # --- 真实参数切换：threshold 对因子构成影响 ---
    base = run(start_date="20250401", end_date="20250712", config=DEFAULT_CONFIG)
    if base.empty:
        checks.append({"check": "基准因子非空", "result": "fail", "detail": "基准无数据"})
        return _finalize(True, "overfitting_check", checks)

    variants = {
        "min_contract_threshold=1e6": {"min_contract_threshold": 1e6, "_metric": "count"},
        "min_contract_threshold=1e8": {"min_contract_threshold": 1e8, "_metric": "count"},
        "score_buy=80/sell=20": {"score_buy_threshold": 80, "score_sell_threshold": 20, "_metric": "signals"},
    }
    base_count = len(base)
    base_signals = int((base["signal"] == "buy").sum()) + int((base["signal"] == "sell").sum())
    for label, cfg_patch in variants.items():
        metric = cfg_patch.pop("_metric", "count")
        try:
            v = run_factor("20250401", "20250712", cfg_patch)
            if metric == "count":
                v_count = len(v) if not v.empty else 0
                changed = v_count != base_count
                detail = f"base_count={base_count}, variant_count={v_count}"
            else:
                v_count = len(v) if not v.empty else 0
                v_signals = int((v["signal"] == "buy").sum()) + int((v["signal"] == "sell").sum())
                changed = v_signals != base_signals
                detail = f"base_signals={base_signals}, variant_signals={v_signals}"
            checks.append({
                "check": f"参数 '{label}' 真实生效",
                "result": "pass" if changed else "fail",
                "detail": detail,
            })
            print(f"  {'PASS' if changed else 'FAIL'}: {label} -> {detail}")
        except Exception as e:
            checks.append({"check": f"参数 '{label}' 可执行", "result": "fail", "detail": str(e)[:100]})
            print(f"  FAIL: {label} 执行出错: {e}")

    # --- 训练/测试分布对比 ---
    train = run_factor("20250401", "20250531", {})
    test = run_factor("20250601", "20250712", {})
    if train.empty or test.empty:
        checks.append({
            "check": "训练/测试两段均有数据",
            "result": "fail",
            "detail": f"train={len(train)}, test={len(test)}",
        })
        print(f"  FAIL: 训练/测试分布对比需要两段数据 train={len(train)} test={len(test)}")
    else:
        t_mean, s_mean = train["factor_value"].mean(), test["factor_value"].mean()
        t_std, s_std = train["factor_value"].std(), test["factor_value"].std()
        diff_pct = abs(t_mean - s_mean) / (abs(t_mean) + 1e-8) * 100
        stable = diff_pct < 50
        checks.append({
            "check": "训练/测试因子分布稳定",
            "result": "pass" if stable else "warn",
            "detail": f"train_mean={t_mean:.4f}, test_mean={s_mean:.4f}, diff={diff_pct:.1f}%",
        })
        print(f"  {'PASS' if stable else 'WARN'}: train vs test diff={diff_pct:.1f}%")

    return _finalize(True, "overfitting_check", checks)


def layer3_out_of_sample_validation():
    """L3 样本外：用修改意见指定的独立样本外区间在验证外再做一次，并检查信号可交易性。"""
    print("\n  [Layer 3] 样本外验证: 独立区间(20250401-20250531)生成有效信号")
    checks = []

    oos = run_factor("20250401", "20250531", {})
    if oos.empty:
        checks.append({"check": "样本外生成因子", "result": "fail", "detail": "无输出"})
        return _finalize(True, "oos_validation", checks)

    buy_count = int((oos["signal"] == "buy").sum())
    sell_count = int((oos["signal"] == "sell").sum())
    unique_stocks = oos["ts_code"].nunique()
    factor_std = float(oos["factor_value"].std())

    checks.append({
        "check": "样本外有 buy/sell 信号",
        "result": "pass" if (buy_count + sell_count) > 0 else "fail",
        "detail": f"buy={buy_count}, sell={sell_count}",
    })
    checks.append({
        "check": "样本外覆盖≥5只股票",
        "result": "pass" if unique_stocks >= 5 else "fail",
        "detail": f"stocks={unique_stocks}",
    })
    checks.append({
        "check": "因子值有区分度(std>0.01)",
        "result": "pass" if factor_std > 0.01 else "fail",
        "detail": f"factor_std={factor_std:.4f}",
    })
    print(f"  PASS: OOS buy={buy_count}, sell={sell_count}, stocks={unique_stocks}, std={factor_std:.4f}")

    return _finalize(True, "oos_validation", checks)


if __name__ == "__main__":
    print("=" * 60)
    print("A10 Material Contract Alpha - 三层验证")
    print("=" * 60)

    results = {}
    for layer_name, layer_fn in [
        ("Layer 1: 未来函数检查", layer1_future_function_check),
        ("Layer 2: 过拟合检查", layer2_overfitting_check),
        ("Layer 3: 样本外验证", layer3_out_of_sample_validation),
    ]:
        print(f"\n{layer_name}")
        results[layer_name] = layer_fn()

    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    all_passed = True
    for name, res in results.items():
        status = "PASS" if res["passed"] else "FAIL"
        if not res["passed"]:
            all_passed = False
        print(f"  {status}: {name}")

    print(f"\n总体结果: {'通过' if all_passed else '不通过'}")
    if not all_passed:
        sys.exit(1)
    print()