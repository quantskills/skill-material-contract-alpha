# Material Contract Alpha Data Guide

## Data Source
- **API**: `panda_data.readers.market_reference_reader.get_stock_material_contract()`（回测行情：`get_stock_daily_pre` 前复权）
- **Base URL**: `http://pandadata.pandaaiquant.com` (via `PANDA_DATA_BASE_URL`)
- **Auth**: Environment variables (not hardcoded)

## Authentication

```python
import os
import panda_data

username = os.environ["PANDA_DATA_USERNAME"]
password = os.environ["PANDA_DATA_PASSWORD"]
base_url = os.environ.get("PANDA_DATA_BASE_URL", "http://pandadata.pandaaiquant.com")
panda_data.init_token(username=username, password=password, base_url=base_url)
```

**Environment Variables:**
| Variable | Required | Default | Description |
|---|---|---|---|
| `PANDA_DATA_USERNAME` | Yes | — | Phone number (86 format) |
| `PANDA_DATA_PASSWORD` | Yes | — | PandaData password |
| `PANDA_DATA_BASE_URL` | No | http://pandadata.pandaaiquant.com | API base URL |

## Method Signature
```python
get_stock_material_contract(
    start_date: str = None,
    end_date: str = None,
    symbol: Optional[Union[str, List[str]]] = None,
    fields: Optional[Union[str, List[str]]] = None,
) -> pd.DataFrame
```

## Key Fields for Alpha
| Field | Type | Description |
|---|---|---|
| symbol | str | Stock code |
| info_date | str | Announcement date (YYYYMMDD) |
| max_contract_amount | float | Max contract amount |
| min_contract_amount | float | Min contract amount |
| currency | str | Currency |
| project_progress | int | 1=draft, 2=signed, 3=in progress, 4=completed |
| contract_title | str | Contract name |
| party_b_relation | str | Related party relationship |

## Standard Output Fields

| Field | Type | Description |
|---|---|---|
| trade_date | str | Signal date (YYYYMMDD) |
| asset_type | str | "stock" |
| ts_code | str | Stock code with suffix |
| factor_id | str | "A10" |
| factor_name | str | "material-contract-alpha" |
| factor_value | float | `log1p(sum(max_contract_amount))` |
| score | float | 0-100 standardized score |
| rank | int | Cross-sectional rank (1=best) |
| signal | str | "buy" / "sell" / "hold" |
| confidence | float | 0-1 confidence level |
| data_version | str | Dataset version identifier |
| update_time | str | Computation timestamp |

## Factor Calculation Formula
```
contract_amount = max(max_contract_amount, min_contract_amount)  # 每笔公告取大
factor_value = log1p(sum(contract_amount))  # 当日股票级汇总后取对数
score = (factor_value - min) / (max - min) * 100
rank = descending rank by factor_value
signal = buy if score >= 70, sell if score <= 30, hold otherwise
```

## Signal Generation
- `score >= 70`: buy signal
- `score <= 30`: sell signal
- otherwise: hold

## 3-Layer Validation Process

### Layer 1: Future Function Check
- Verifies `trade_date` matches `max(info_date)` in raw data
- No future data leakage by construction (uses announcement date)
- Output: passed/warn with date comparison detail

### Layer 2: Overfitting Check
- Parameter sensitivity test (vary min_contract_threshold)
- Train/test split comparison (factor value distribution)
- Stability check across time periods

### Layer 3: Out-of-Sample Validation
- Test set must generate valid buy/sell signals
- Must cover >= 5 stocks cross-sectionally
- Factor value must have std > 0.01 (cross-sectional differentiation)

## Validation Output
```python
{
  "passed": bool,
  "detail": str,
  "checks": [
    {"check": str, "result": "pass"|"warn"|"skip", "detail": str},
    ...
  ]
}
```
