import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor import run as run_factor
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# A10 回测
# 关键规则：信号在 t 日公告后收盘形成，只能在 t+1（下一交易日）成交，
# 收益一律从信号日的下一个交易日开始计算（前视偏差规避）。
# ============================================================


def get_stock_daily_data(start_date: str, end_date: str, symbols) -> pd.DataFrame:
    """从 market_reader 导入 get_stock_daily_pre（前复权）拉取行情。

    使用前复权行情，避免分红/送转除权日 (close-pre_close)/pre_close 被除权缺口扭曲，
    导致 t+1 收益计算失真。
    """
    from panda_data.readers.market_reader import get_stock_daily_pre
    daily = get_stock_daily_pre(
        symbol=symbols if isinstance(symbols, list) else None,
        start_date=start_date,
        end_date=end_date,
    )
    if daily is None or daily.empty:
        return pd.DataFrame()
    daily = daily.rename(columns={"date": "trade_date"})
    daily["trade_date"] = daily["trade_date"].astype(str)
    for col in ["close", "pre_close", "open", "limit_up", "limit_down", "trade_status"]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")
    return daily


def forward_return_shift(signal_df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """把每个信号日 t 对接到 t 的下一个交易日收益。

    daily 需含每只股票的整段连续交易日序列（前复权行情）；对每只股票按日期排序后
    用相邻复权收盘价计算日收益（前复权行情中 pre_close 为未复权昨收，不能直接相除），
    shift(-1) 得到『下一交易日』的收益率与收盘价，作为 t+1 的可实现收益。
    同时检查 t+1 是否一字涨停/停牌（trade_status!=0 或开盘价=涨停价）——不可成交。
    """
    if signal_df.empty or daily.empty:
        return pd.DataFrame()

    daily = daily.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    # 前复权行情：close 为复权收盘价，pre_close 为未复权昨收。
    # 用相邻复权收盘价计算收益率，分红/送转除权自然并入，不产生假跳变。
    g_all = daily.groupby("symbol")
    daily["pct_chg"] = g_all["close"].pct_change() * 100

    g = daily.groupby("symbol", as_index=False)
    daily["next_date"] = g["trade_date"].shift(-1)
    daily["next_close"] = g["close"].shift(-1)
    daily["next_open"] = g["open"].shift(-1)
    daily["next_pct"] = g["pct_chg"].shift(-1)
    daily["next_limit_up"] = g["limit_up"].shift(-1)
    daily["next_trade_status"] = g["trade_status"].shift(-1)

    next_df = daily[["symbol", "trade_date", "next_date", "next_close",
                     "next_open", "next_pct", "next_limit_up", "next_trade_status"]]
    sig = signal_df.rename(columns={"ts_code": "symbol"})

    m = sig.merge(next_df, on=["symbol", "trade_date"], how="left")
    m["tradable"] = (
        m["next_date"].notna()
        & m["next_trade_status"].eq(0)
        & (~(m["next_open"].eq(m["next_limit_up"]) & m["next_open"].notna()))
    )
    m["fwd_ret"] = np.where(m["tradable"], m["next_pct"], np.nan)
    return m


def calc_ic(m):
    merged = m.dropna(subset=["factor_value", "fwd_ret"])
    if len(merged) < 10:
        return {"ic": np.nan, "rank_ic": np.nan, "count": len(merged)}
    corr = merged["factor_value"].corr(merged["fwd_ret"])
    rank_corr = merged["factor_value"].corr(merged["fwd_ret"], method="spearman")
    return {"ic": corr, "rank_ic": rank_corr, "count": len(merged)}


def calc_icir(ic_values):
    ic_values = [v for v in ic_values if not np.isnan(v)]
    if len(ic_values) < 2:
        return np.nan
    return float(np.mean(ic_values) / (np.std(ic_values, ddof=1) + 1e-10))


def calc_layered_returns(m):
    m = m.copy()
    m2 = m.dropna(subset=["factor_value", "fwd_ret"])
    if m2.empty:
        return {}
    m2["layer"] = pd.qcut(m2["factor_value"], 5, labels=["L1", "L2", "L3", "L4", "L5"], duplicates="drop")
    if m2["layer"].nunique() < 2:
        return {}
    layer_returns = m2.groupby("layer")["fwd_ret"].mean().to_dict()
    layer_std = m2.groupby("layer")["fwd_ret"].std().to_dict()
    l1 = m2[m2["layer"] == "L1"]["fwd_ret"]
    l5 = m2[m2["layer"] == "L5"]["fwd_ret"]
    ls = l5.mean() - l1.mean() if len(l1) > 0 and len(l5) > 0 else np.nan
    return {
        "layer_returns": {k: float(v) for k, v in layer_returns.items()},
        "layer_std": {k: float(v) for k, v in layer_std.items()},
        "long_short_return": float(ls) if not np.isnan(ls) else None,
    }


def calc_max_drawdown(returns):
    if returns.empty:
        return np.nan
    cum = (1 + returns / 100).cumprod()
    peak = cum.expanding().max()
    dd = (cum - peak) / peak
    return float(dd.min() * 100)


def calc_portfolio_drawdown(m) -> float:
    """按信号日构建每天等权组合（当日可交易 top20% 股票），
    以组合日收益序列计算最大回撤，避免把不同日期的收益误当同一资金曲线。"""
    m = m.copy()
    m = m.dropna(subset=["fwd_ret"])
    daily_rets = []
    for date, grp in m.groupby("trade_date"):
        if grp.empty:
            continue
        top = grp.sort_values("rank").head(int(np.ceil(len(grp) * 0.2)))
        if len(top) == 0:
            continue
        daily_rets.append(top["fwd_ret"].mean())
    if not daily_rets:
        return np.nan
    returns = pd.Series(daily_rets)
    dev = calc_max_drawdown(returns)
    return dev


def calc_turnover(m) -> float:
    """换手率：相邻信号日 top 20% 组合的成分股平均替换率。
    每日截面内按 rank（越小越好）取前 20% 为当日组合，
    换手率 = 1 - 连续两日持仓交集/前一日持仓数，全部日期平均。"""
    m = m.copy()
    m = m.dropna(subset=["fwd_ret"])
    m = m.sort_values(["trade_date", "rank"])
    portfolio_by_date = {}
    for date, grp in m.groupby("trade_date"):
        n_top = max(1, int(np.ceil(len(grp) * 0.2)))
        portfolio_by_date[date] = set(grp.head(n_top)["symbol"].tolist())
    dates = sorted(portfolio_by_date.keys())
    if len(dates) < 2:
        return np.nan
    turn_values = []
    for i in range(len(dates) - 1):
        prev, nxt = portfolio_by_date[dates[i]], portfolio_by_date[dates[i + 1]]
        if not prev:
            continue
        turn_values.append(1 - len(prev & nxt) / len(prev))
    if not turn_values:
        return np.nan
    return float(np.mean(turn_values) * 100)


def extend_date(date_str: str, days: int = 15) -> str:
    """把 YYYYMMDD 往后推 days 天，保证取到 t+1 之后的行情。"""
    d = pd.to_datetime(date_str, format="%Y%m%d") + pd.Timedelta(days=days)
    return d.strftime("%Y%m%d")


def extend_date_until(sig_end: str, ret_end: str) -> str:
    """行情区间右端点：取 ret_end（已晚于信号段）再向后延伸，覆盖最后一个信号日的 t+1。"""
    return extend_date(ret_end, 15)


def run_backtest_summary() -> dict:
    """执行完整回测并返回结构化统计（供回测报告与发布验收报告使用）。"""
    periods = [
        ("20250303", "20250331", "20250303", "20250430"),
        ("20250401", "20250531", "20250401", "20250630"),
        ("20250601", "20250731", "20250601", "20250815"),
    ]

    all_m = []
    ic_records = []
    period_records = []
    errors = []

    for sig_start, sig_end, ret_start, ret_end in periods:
        try:
            result = run_factor(start_date=sig_start, end_date=sig_end)
        except Exception as e:
            errors.append(f"因子计算 {sig_start}~{sig_end}: {e}")
            continue
        if result.empty:
            errors.append(f"信号区间 {sig_start}~{sig_end} 无数据")
            continue

        symbols = list(dict.fromkeys(result["ts_code"].tolist()))
        try:
            daily = get_stock_daily_data(ret_start, extend_date_until(sig_end, ret_end), symbols)
        except Exception as e:
            errors.append(f"行情拉取 {ret_start}~{ret_end}: {e}")
            continue
        if daily.empty:
            errors.append(f"收益区间 {ret_start}~{ret_end} 无行情")
            continue

        m = forward_return_shift(result, daily)
        if m.empty or m["tradable"].sum() == 0:
            errors.append(f"{sig_start}~{sig_end} 无法对接 t+1 收益")
            continue

        m["period_start"], m["period_end"] = sig_start, sig_end
        all_m.append(m)

        ic_res = calc_ic(m)
        if ic_res["count"] > 0:
            ic_records.append(ic_res)
        period_records.append({
            "period": f"{sig_start}~{sig_end}",
            "signal_count": int(len(m)),
            "tradable_count": int(m["tradable"].sum()),
            "ic": ic_res["ic"] if ic_res["count"] > 0 else None,
            "rank_ic": ic_res["rank_ic"] if ic_res["count"] > 0 else None,
        })

    summary = {
        "periods": period_records,
        "errors": errors,
        "total_signals": 0,
        "tradable_signals": 0,
        "stocks": 0,
        "signal_dist": {"buy": 0, "sell": 0, "hold": 0},
        "ic": None,
        "rank_ic": None,
        "icir": None,
        "ic_std": None,
        "layers": {},
        "long_short_return": None,
        "max_drawdown": None,
        "turnover": None,
        "sample": None,
    }

    if not all_m:
        return summary

    m_all = pd.concat(all_m, ignore_index=True)
    m_valid = m_all.dropna(subset=["factor_value", "fwd_ret"]).copy()

    summary["total_signals"] = int(len(m_all))
    summary["tradable_signals"] = int(len(m_valid))
    summary["stocks"] = int(m_valid["symbol"].nunique())
    summary["signal_dist"] = {
        "buy": int((m_valid["signal"] == "buy").sum()),
        "sell": int((m_valid["signal"] == "sell").sum()),
        "hold": int((m_valid["signal"] == "hold").sum()),
    }
    summary["sample"] = m_valid

    if ic_records:
        ic_values = [r["ic"] for r in ic_records]
        rank_ic_v = [r["rank_ic"] for r in ic_records]
        summary["ic"] = float(np.mean(ic_values))
        summary["rank_ic"] = float(np.mean(rank_ic_v))
        summary["icir"] = calc_icir(ic_values)
        if len(ic_values) >= 2:
            summary["ic_std"] = float(np.std(ic_values, ddof=1))
        summary["ic_periods"] = len(ic_records)

    layer_result = calc_layered_returns(m_valid)
    if layer_result:
        summary["layers"] = layer_result["layer_returns"]
        summary["layers_std"] = layer_result["layer_std"]
        summary["layer_short"] = layer_result["long_short_return"]

    summary["max_drawdown"] = calc_portfolio_drawdown(m_valid)
    summary["turnover"] = calc_turnover(m_valid)

    buy_ret = m_valid.loc[m_valid["signal"] == "buy", "fwd_ret"]
    summary["buy_avg_ret"] = float(buy_ret.mean()) if len(buy_ret) else None
    summary["buy_win_rate"] = float((buy_ret > 0).mean() * 100) if len(buy_ret) else None
    return summary


def run_backtest():
    period_labels = []

    print("=" * 60)
    print("A10 Material Contract Alpha - 回测报告 (收益 t+1 起算)")
    print("=" * 60)

    summary = run_backtest_summary()

    for p in summary["periods"]:
        print(f"  OK: signal {p['period']} -> {p['signal_count']} 条, t+1 可交易 {p['tradable_count']} 条")
    for e in summary["errors"]:
        print(f"  WARN: {e}")

    m_valid = summary["sample"]
    if m_valid is None or m_valid.empty:
        print("无可用数据，无法生成回测报告")
        return

    print(f"\n总信号数: {summary['total_signals']}")
    print(f"可交易(有t+1收益): {summary['tradable_signals']}")
    print(f"覆盖股票: {summary['stocks']}")
    dist = summary["signal_dist"]
    print(f"信号分布: buy={dist['buy']}, sell={dist['sell']}, hold={dist['hold']}")

    if summary["ic"] is not None:
        print(f"\nIC 计算期数: {summary.get('ic_periods')}")
        print(f"IC (均值): {summary['ic']:.4f}")
        print(f"Rank IC (均值): {summary['rank_ic']:.4f}")
        icir = summary["icir"]
        print(f"ICIR: {icir:.4f}" if icir is not None and not np.isnan(icir) else "ICIR: N/A (期数不足)")
        print(f"IC 标准差: {summary['ic_std']:.4f}" if summary["ic_std"] is not None else "IC 标准差: N/A")
    else:
        print("\nIC: N/A")

    if summary.get("layers"):
        print(f"\n分层收益 (L1=低因子值 ~ L5=高因子值, t+1起算):")
        for layer_name in ["L1", "L2", "L3", "L4", "L5"]:
            ret = summary["layers"].get(layer_name)
            std = summary["layers_std"].get(layer_name)
            if ret is not None:
                print(f"  {layer_name}: {ret:.4f}% (std={std:.4f}%)")
        if summary["layer_short"] is not None:
            print(f"  多空收益 (L5-L1): {summary['layer_short']:.4f}%")
    else:
        print("\n分层收益: N/A")

    max_dd = summary["max_drawdown"]
    print(f"\n最大回撤 (可交易信号t+1收益): {max_dd:.2f}%" if max_dd is not None and not np.isnan(max_dd) else "\n最大回撤: N/A")

    turnover = summary["turnover"]
    print(f"换手率 (top 20% 按 rank): {turnover:.2f}%")

    print(f"\n--- 信号样例 (score 前10) ---")
    cols = [c for c in ["symbol", "trade_date", "factor_value", "score", "rank", "signal",
                        "next_date", "fwd_ret", "tradable"] if c in m_valid.columns]
    print(m_valid.sort_values("score", ascending=False).head(10)[cols].to_string(index=False))

    gate_pass = summary["tradable_signals"] >= 30
    print(f"\n=== 回测完成 | 样本量={'足够' if gate_pass else '不足'} ===")


if __name__ == "__main__":
    run_backtest()