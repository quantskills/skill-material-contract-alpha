# Material Contract Alpha - Portable Loader

## Quick Start

```bash
# Set auth
export PANDA_DATA_USERNAME="your_phone"
export PANDA_DATA_PASSWORD="your_password"
export PANDA_DATA_BASE_URL="http://pandadata.pandaaiquant.com"
# Windows: $env:PANDA_DATA_USERNAME = "..."

# Run factor
python scripts/factor.py

# Validate
python scripts/validate.py

# Backtest
python scripts/backtest.py
```

## Files

| File | Purpose |
|---|---|
| scripts/factor.py | Factor computation (env var auth, standard columns) |
| scripts/validate.py | 3-layer validation (future, overfitting, OOS) |
| scripts/backtest.py | Full backtest metrics (IC/ICIR, layered, drawdown, turnover) |
| scripts/build_release.py | Production release and acceptance report |
| references/data_guide.md | Data field documentation |

## Output

Production parquet: `生产产物/数据库.parquet`
Acceptance report: `生产产物/发布验收报告.md`, `生产产物/发布验收报告.json`
