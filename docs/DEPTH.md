# 深度登记 水产拍卖结算

规模：中型。使用者：水产批发市场结算员。核心规则：先毛皮配对，再扣杂计价，按更正链选择唯一生效版，只支付差额。拼车票按户级货包拆账：当日结价先按当前有效货包发布，补筐晚到重跑出新版，逐户影响留痕。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 称重采信 | 查看并执行称重采信 | `POST /api/intake` | `app/modules/intake/rules.py` | `tests/test_intake.py` |
| M2 货品换算 | 查看并执行货品换算 | `POST /api/conversion` | `app/modules/conversion/rules.py` | `tests/test_conversion.py` |
| M3 毛皮配对 | 查看并执行毛皮配对 | `POST /api/pairing` | `app/modules/pairing/rules.py` | `tests/test_pairing.py` |
| M4 扣杂竞价 | 查看并执行扣杂竞价 | `POST /api/auction` | `app/modules/auction/rules.py` | `tests/test_auction.py` |
| M5 更正裁决 | 查看并执行更正裁决 | `POST /api/correction` | `app/modules/correction/rules.py` | `tests/test_correction.py` |
| M6 应付对账 | 查看并执行应付对账 | `POST /api/reconcile` | `app/modules/reconcile/rules.py` | `tests/test_reconcile.py` |
| M7 结算归档 | 查看并执行结算归档 | `POST /api/archive` | `app/modules/archive/rules.py` | `tests/test_archive.py` |
| M8 拼车拆账 | 查看拆账并发布户级结算 | `POST /api/split`、`POST /api/split/{票号}/publish` | `app/modules/split/rules.py` | `tests/test_split.py`、`tests/test_split_publish.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码中文票据 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_legacy_encoding` |
| TRAP-02 | BOM表头 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_bom_real` |
| TRAP-04 | 分段表头 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_repeated_header_real` |
| TRAP-05 | 缺列记录 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_bad_columns_real` |
| TRAP-07 | 空值哨兵 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/conversion/rules.py` | `tests/test_conversion.py::test_sentinel_real` |
| TRAP-08 | 前导零票号 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_leading_zero_real` |
| TRAP-14 | 重复编号不同原值 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_duplicate_conflict_real` |
| TRAP-18 | 三类空态 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/intake/rules.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-15 | 吨与千克混合 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/conversion/rules.py` | `tests/test_conversion.py::test_tonnes_counterexample` |
| TRAP-06 | 全角千分位 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/conversion/rules.py` | `tests/test_conversion.py::test_fullwidth_thousands` |
| TRAP-10 | 金额半分舍入 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/auction/rules.py` | `tests/test_auction.py::test_half_cent_rounding` |
| TRAP-26 | 陈旧更正分支 | 静默错算或丢失证据 | 显式归一与原因裁决 | `app/modules/correction/rules.py` | `tests/test_correction.py::test_stale_branch` |
| TRAP-27 | 货包缺估重 | 静默摊入可发布金额 | 排除出可发布金额并保留证据 | `app/modules/split/rules.py` | `tests/test_split.py::test_missing_est_excluded` |
| TRAP-28 | 同包编号归属冲突 | 按先见者入账 | 全部排除，票无有效货包则阻断发布 | `app/modules/split/rules.py` | `tests/test_split.py::test_attribution_conflict_blocks_ticket` |
| TRAP-29 | 分摊尾差去向不明 | 尾差消失或重复 | 尾差落给份额最大户并标记可溯 | `app/modules/split/rules.py` | `tests/test_split.py::test_tail_traceable_real` |
| TRAP-30 | 补筐晚到 | 压住当日结价不发布 | 先按当前货包发布，补筐重跑出新版，影响留痕 | `app/modules/split/handler.py` | `tests/test_split_publish.py::test_publish_impact_traceable` |
| TRAP-31 | 整筐退运 | 仍按估重摊钱 | 退运货包排除出金额，证据保留 | `app/modules/split/rules.py` | `tests/test_split.py::test_returned_excluded` |
| TRAP-32 | 重复发布同一内容 | 版本号虚增 | 内容摘要一致则幂等返回旧版 | `app/modules/split/handler.py` | `tests/test_split_publish.py::test_publish_idempotent_no_new_results` |

## 拼车拆账规则

货包 CSV（`<样例>.split.csv` 或 `split_csv_text`）列：id、ticket、household、baskets、est_kg、price、flag（正常/补筐/退运）。同编号同值去重，异值全部按归属冲突排除。缺估重、归属冲突、退运、票未生效的货包不进入可发布金额，全部留证据。
户暂计=Σ(估重×成交单价) 按货包逐条量化到 0.01CNY 后求和。差额=车票应付−暂计合计，按暂计金额比例分摊（暂计全零改按估重，再全零按户均摊），尾差落给份额最大户。每户可发布金额=暂计+分摊+尾差，户级合计恒等于车票应付（完整覆盖），不满足则禁止发布。
发布按票版本化：内容摘要与最新版一致则幂等不新增；base_version 与当前不一致返回 409；校验失败不写库，旧版保留。补筐到达后重跑该批得到新批号，再发布生成下一版，impact 记录逐户增减。

## 对账规则

输入=采纳原始行+隔离行+空行+同值重复行+重复表头。计价版本总额与生效票总额分别展示，避免把更正前后重复求和。最终应付=已付+待付，负待付为退款。

## 已知不覆盖

无称重设备实时接入，采用现场导出文件。无支付执行，只生成可复核结算证据。
