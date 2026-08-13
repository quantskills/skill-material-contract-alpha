# 重大合同 Alpha 因子 Skill

**简体中文** | [English](README.en.md)

> 基于重大合同金额的横截面排序 Alpha 因子：log1p(累计合同金额) 横截面标准化，生成 buy/sell/hold 信号。

<p align="center">
  <img alt="factor id" src="https://img.shields.io/badge/factor_id-A10-blue">
  <img alt="data source" src="https://img.shields.io/badge/data-Pandadata-ff69b4">
  <img alt="validation" src="https://img.shields.io/badge/validation-3%20layer-brightgreen">
</p>

---

## 这是什么

`material-contract-alpha` 是一个 **Alpha 因子技能**：调用 PandaData 重大合同接口，对 `total_amount` 做 log1p 变换后，在横截面上做 z-score 标准化，生成每日的 buy/sell/hold 信号。

## 因子计算流程

```
原始合同金额 → 按股票聚合(sum) → log1p 变换 → 横截面 z-score 标准化
→ buy(>+1σ) / sell(<-1σ) / hold(中间)
```

## 验证体系（三层沙漏）

| 层级 | 脚本 | 内容 |
|---|---|---|
| L1 未来函数 | `validate.py` | 检查 t+1 是否用 t 数据、信息比率是否异常 |
| L2 过拟合 | `validate.py` | 分组相关性检验、子样本稳定性 |
| L3 样本外 | `validate.py` | 时间序列分割验证 |

## 回测指标

| 指标 | 说明 |
|---|---|
| IC / ICIR | 因子与下期收益的相关系数 |
| 分层收益 | L1-L5 五层平均收益 |
| 多空收益 | L5 做多 + L1 做空 |
| 最大回撤 | buy 信号的累计回撤 |
| 换手率 | 信号变更频率 |

## 快速开始

```bash
# 设置凭据（首次）
export PANDA_DATA_USERNAME=your_phone
export PANDA_DATA_PASSWORD=your_password
export PANDA_DATA_BASE_URL=http://pandadata.pandaaiquant.com

# 生成因子
python scripts/factor.py

# 验证
python scripts/validate.py

# 回测
python scripts/backtest.py

# 发布
python scripts/build_release.py
```

### 输出字段

| 字段 | 说明 |
|---|---|
| `trade_date` | 因子日期 |
| `asset_type` | `stock` |
| `ts_code` | 股票代码 |
| `factor_id` | `A10` |
| `factor_value` | z-score 标准化值 |
| `signal` | `buy`/`sell`/`hold` |

## 目录结构

```
material-contract-alpha/
├── SKILL.md                    # 技能入口
├── scripts/
│   ├── factor.py               # 因子计算
│   ├── validate.py             # 三层沙漏验证
│   ├── backtest.py             # 完整回测
│   └── build_release.py        # 发布验收
├── agents/
│   ├── openai.yaml
│   ├── cursor-rule.mdc
│   └── portable-loader.md
├── 生产产物/
│   ├── SKILL.md                # 生产版文档
│   ├── 数据库.parquet          # 因子数据
│   ├── 发布验收报告.md          # 验收报告
│   └── 发布验收报告.json        # 验收数据
└── skill.json                  # 技能元数据
```

## 免责声明

本技能输出为基于公开数据的量化研究支持，不构成任何投资建议。
