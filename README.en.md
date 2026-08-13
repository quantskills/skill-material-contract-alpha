# Material Contract Alpha Factor Skill

[简体中文](README.md) | **English**

> A cross-sectional ranking alpha factor based on material contract amounts: log1p(total contract amount) cross-sectionally normalized to generate buy/sell/hold signals.

<p align="center">
  <img alt="factor id" src="https://img.shields.io/badge/factor_id-A10-blue">
  <img alt="data source" src="https://img.shields.io/badge/data-Pandadata-ff69b4">
  <img alt="validation" src="https://img.shields.io/badge/validation-3%20layer-brightgreen">
</p>

---

## What is this

`material-contract-alpha` is an **Alpha factor skill**: call PandaData's material contract API, apply log1p transformation to `total_amount`, z-score normalize cross-sectionally, and generate daily buy/sell/hold signals.

## Factor Calculation Flow

```
Raw contract amount → Aggregate by stock (sum) → log1p transform
→ Cross-sectional z-score normalization
→ buy(>+1σ) / sell(<-1σ) / hold(middle)
```

## Validation (3-Layer Hourglass)

| Layer | Script | Content |
|---|---|---|
| L1 Look-ahead | `validate.py` | Check t+1 uses t data, no anomalous IR |
| L2 Overfit | `validate.py` | Group correlation test, sub-sample stability |
| L3 Out-of-sample | `validate.py` | Time-series split validation |

## Backtest Metrics

| Metric | Description |
|---|---|
| IC / ICIR | Factor-next-period return correlation |
| Layer returns | L1-L5 quintile average returns |
| Long-short | L5 long + L1 short |
| Max drawdown | Cumulative drawdown of buy signals |
| Turnover | Signal change frequency |

## Quick Start

```bash
# Set credentials (first time)
export PANDA_DATA_USERNAME=your_phone
export PANDA_DATA_PASSWORD=your_password
export PANDA_DATA_BASE_URL=http://pandadata.pandaaiquant.com

# Generate factor
python scripts/factor.py

# Validate
python scripts/validate.py

# Backtest
python scripts/backtest.py

# Release
python scripts/build_release.py
```

### Output Fields

| Field | Description |
|---|---|
| `trade_date` | Factor date |
| `asset_type` | `stock` |
| `ts_code` | Stock symbol |
| `factor_id` | `A10` |
| `factor_value` | Z-score normalized value |
| `signal` | `buy`/`sell`/`hold` |

## Directory Layout

```
material-contract-alpha/
├── SKILL.md                    # Skill entry
├── scripts/
│   ├── factor.py               # Factor calculation
│   ├── validate.py             # 3-layer validation
│   ├── backtest.py             # Full backtest
│   └── build_release.py        # Release report
├── agents/
│   ├── openai.yaml
│   ├── cursor-rule.mdc
│   └── portable-loader.md
├── 生产产物/
│   ├── SKILL.md                # Production doc
│   ├── 数据库.parquet          # Factor data
│   ├── 发布验收报告.md          # Acceptance report
│   └── 发布验收报告.json        # Acceptance data
└── skill.json                  # Skill metadata
```

## Disclaimer

This skill produces quantitative research support based on public data. Nothing here constitutes investment advice.
