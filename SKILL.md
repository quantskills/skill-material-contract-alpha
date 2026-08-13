---
name: material-contract-alpha
description: A-share material contract alpha factor skill — generates trading signals based on major contract announcements. Use when the user asks to calculate material contract alpha, generate contract-based signals, scan for recent major contract announcements, or evaluate contract-driven trading opportunities.
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: skill-material-contract-alpha
  repository_url: https://github.com/quantskills/skill-material-contract-alpha
  project_type: skill
  collection: material-contract-alpha
  creator: fuzijun
  maintainer: fuzijun
quantSkills:
  project_type: skill
  category: factor
  tags:
    - a-share
    - alpha
    - material-contract
    - factor
    - pandadata
  platforms:
    - claude-code
    - codex
    - openclaw
    - cursor
  status: draft
  requires:
    - skill-pandadata-api
  validation_level: listed
  maintainer_type: community
  summary_zh: "A 股重大合同 Alpha 因子：基于合同金额对数和的横截面排序信号。"
  summary_en: "A-share material contract alpha factor: cross-sectional ranking based on log-sum of contract amounts."
---

# Material Contract Alpha

Use this skill to calculate an alpha factor based on material contract announcements. When a company announces major contracts, the contract amount signals potential revenue impact.

## Factor Logic
- **Core Hypothesis**: Major contract announcements convey private information about future revenue.
- **Formula**: `factor_value = log1p(sum(max(max_contract_amount, min_contract_amount)))`,逐公告金额取大后按日求和（A10 的计算统一用 max 兜底防 min>max 异常） per stock
- **Sort Direction**: Descending (higher = stronger buy signal)
- **Applicable Market**: A-share

## Authentication

PandaAI data 数据拉取库（panda_data）凭据，通过环境变量提供（不写入代码）：

```bash
# Windows PowerShell
$env:PANDA_DATA_USERNAME = "your_phone"
$env:PANDA_DATA_PASSWORD = "your_password"
$env:PANDA_DATA_BASE_URL = "http://pandadata.pandaaiquant.com"
```

```bash
# Linux/Mac
export PANDA_DATA_USERNAME="your_phone"
export PANDA_DATA_PASSWORD="your_password"
export PANDA_DATA_BASE_URL="http://pandadata.pandaaiquant.com"
```

## Input Data
| Field | Description | Source |
|---|---|---|
| start_date | Data start date (YYYYMMDD) | PandaAI data 数据拉取库 |
| end_date | Data end date (YYYYMMDD) | PandaAI data 数据拉取库 |
| symbols | Stock codes (optional) | User config |

因子计算、验证、回测均使用 PandaAI data 数据拉取库（panda_data），不依赖任何本地临时文件或来源不明数据。

## Output
| Field | Description |
|---|---|
| trade_date | Signal date (YYYYMMDD) |
| asset_type | "stock" |
| ts_code | Stock code with suffix |
| factor_id | "A10" |
| factor_name | "material-contract-alpha" |
| factor_value | Raw factor value (log1p of sum contract amount) |
| score | Standardized 0-100 |
| rank | Cross-sectional rank |
| signal | buy / sell / hold |
| confidence | 0-1 confidence level |
| data_version | Dataset version identifier |
| update_time | Computation timestamp |

## Usage
```bash
python scripts/factor.py
python scripts/validate.py
python scripts/backtest.py
```

## Verification Requirements
- Layer 1: No future leakage — every trade_date must be an announcement date (info_date); signals form after t close, returns measured from t+1
- Layer 2: No overfitting — parameter sensitivity with genuinely changed params + train/test distribution
- Layer 3: Out-of-sample — test set generates valid signals
- Backtest metrics: IC, ICIR, layered returns, portfolio max drawdown, turnover, signal samples (all return from t+1)
- Data source: panda_data only

## Tradeable Rule (t+1)
- Signals form at close of signal day t (announcement day)
- Buy/sell only at t+1 open; skip limit-up one-word board, suspension (trade_status != 0), or missing valid price on t+1
- All returns are computed from t+1 (no look-ahead)

## Production
```bash
python scripts/build_release.py
```
- Generates `生产产物/数据库.parquet` (per-announcement-day cross sections)
- Generates `生产产物/发布验收报告.md` and `生产产物/发布验收报告.json` with real multi-day historical backtest stats

## Dependencies
- panda_data >= 0.0.12
- numpy, pandas
