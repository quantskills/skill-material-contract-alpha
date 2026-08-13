import os
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict, Any

FACTOR_ID = "A10"
FACTOR_NAME = "material-contract-alpha"
DATA_VERSION = "pandadata-material-contract-alpha-v1"

STANDARD_COLUMNS = [
    "trade_date", "asset_type", "ts_code", "factor_id", "factor_name",
    "factor_value", "score", "rank", "signal", "confidence",
    "data_version", "update_time",
]

DEFAULT_CONFIG = {
    "min_contract_threshold": 0.0,
    "log_base": None,
    "score_buy_threshold": 70.0,
    "score_sell_threshold": 30.0,
}


def get_panda_client():
    import panda_data
    username = os.environ.get("PANDA_DATA_USERNAME")
    password = os.environ.get("PANDA_DATA_PASSWORD")
    base_url = os.environ.get("PANDA_DATA_BASE_URL", "http://pandadata.pandaaiquant.com")
    if not username or not password:
        raise ValueError(
            "请设置环境变量 PANDA_DATA_USERNAME 和 PANDA_DATA_PASSWORD"
        )
    panda_data.init_token(username=username, password=password, base_url=base_url)
    return panda_data


def get_material_contract_data(
    start_date: str,
    end_date: str,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """从 market_reference_reader 导入 get_stock_material_contract 拉取重大合同数据。"""
    panda = get_panda_client()
    from panda_data.readers.market_reference_reader import get_stock_material_contract
    return get_stock_material_contract(
        symbol=symbols,
        start_date=start_date,
        end_date=end_date,
        fields=[
            "symbol", "name", "info_date", "max_contract_amount",
            "min_contract_amount", "currency", "contract_title",
            "project_name", "project_progress",
        ],
    )


def calculate_alpha(
    df_contract: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    if df_contract.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    cfg = {**DEFAULT_CONFIG, **(config or {})}

    df = df_contract.copy()
    df["info_date"] = pd.to_datetime(df["info_date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["info_date"])

    df["max_contract_amount"] = pd.to_numeric(
        df["max_contract_amount"], errors="coerce"
    ).fillna(0)
    df["min_contract_amount"] = pd.to_numeric(
        df["min_contract_amount"], errors="coerce"
    ).fillna(0)

    df["contract_amount"] = df[["max_contract_amount", "min_contract_amount"]].max(axis=1)

    min_threshold = float(cfg["min_contract_threshold"])
    df = df[df["contract_amount"] >= min_threshold]
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    log_base = cfg.get("log_base")

    # 逐信息日生成当日横截面信号（当日公告 -> 当日末收盘形成信号 -> t+1 可成交）
    frames = []
    for info_date, day_group in df.groupby("info_date"):
        contract_sum = (
            day_group.groupby("symbol")
            .agg(
                contract_count=("symbol", "count"),
                total_amount=("contract_amount", "sum"),
                avg_amount=("contract_amount", "mean"),
                max_single_amount=("contract_amount", "max"),
            )
            .reset_index()
        )

        raw = contract_sum["total_amount"].replace(0, np.nan)
        if log_base is not None and log_base > 1:
            contract_sum["factor_value"] = np.log(raw) / np.log(log_base)
        else:
            contract_sum["factor_value"] = np.log1p(contract_sum["total_amount"])

        values = contract_sum["factor_value"].replace([np.inf, -np.inf], 0)
        if values.std() > 0:
            contract_sum["score"] = (
                (values - values.min()) / (values.max() - values.min()) * 100
            )
        else:
            contract_sum["score"] = 50.0

        contract_sum["rank"] = values.rank(ascending=False, method="min").astype(int)

        buy_th = float(cfg["score_buy_threshold"])
        sell_th = float(cfg["score_sell_threshold"])
        conditions = [
            contract_sum["score"] >= buy_th,
            contract_sum["score"] <= sell_th,
        ]
        choices = ["buy", "sell"]
        contract_sum["signal"] = np.select(conditions, choices, default="hold")

        values_range = values.max() - values.min()
        contract_sum["confidence"] = np.where(
            values_range > 0,
            ((values - values.min()) / values_range).clip(0, 1),
            0.5,
        )

        contract_sum["info_date"] = info_date
        frames.append(contract_sum)

    if not frames:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    result = result.rename(columns={"symbol": "ts_code", "info_date": "trade_date"})
    result["trade_date"] = result["trade_date"].dt.strftime("%Y%m%d")
    result["asset_type"] = "stock"
    result["factor_id"] = FACTOR_ID
    result["factor_name"] = FACTOR_NAME
    result["data_version"] = DATA_VERSION
    result["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    available_cols = [c for c in STANDARD_COLUMNS if c in result.columns]
    return (
        result[available_cols]
        .sort_values(["trade_date", "score"], ascending=[True, False])
        .reset_index(drop=True)
    )


def run(
    start_date: str,
    end_date: str,
    symbols: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    df_contract = get_material_contract_data(start_date, end_date, symbols)
    return calculate_alpha(df_contract, config)


if __name__ == "__main__":
    result = run(
        start_date="20250701",
        end_date="20250712",
    )
    if not result.empty:
        print(f"Total stocks with contracts: {len(result)}")
        print(f"Buy signals: {len(result[result['signal'] == 'buy'])}")
        print(f"Sell signals: {len(result[result['signal'] == 'sell'])}")
        print(f"Hold signals: {len(result[result['signal'] == 'hold'])}")
        print("\nTop 10 by score:")
        cols = [c for c in result.columns if c != "update_time"]
        print(result[cols].head(10).to_string())
    else:
        print("No data returned")
