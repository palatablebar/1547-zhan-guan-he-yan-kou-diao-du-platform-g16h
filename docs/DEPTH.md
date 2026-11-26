# 展馆核验口调度台验证目录

AI/ML · 传统ML · 中型

修改业务链路时先检查受影响模块的测试，再运行整套 `pytest`。回归记录须能够定位到具体单据或计算值。

## 功能模块

| 编号 | 功能 | 核对内容 | 核心文件 | 独立测试 |
|---|---|---|---|---|
| M1 | 入口排班 | 单据版次与隔离 | `src/venuegate/entry_rotations/service.py` | `tests/test_entry_rotations.py` |
| M2 | 预约批窗 | 截止日和成熟标签 | `src/venuegate/ticket_windows/service.py` | `tests/test_ticket_windows.py` |
| M3 | 到场因子 | 原始数据到特征 | `src/venuegate/arrival_exposure/service.py` | `tests/test_arrival_exposure.py` |
| M4 | 到场人数 | 训练及可重复推断 | `src/venuegate/visitor_counts/service.py` | `tests/test_visitor_counts.py` |
| M5 | 入场回放 | 回放误差、入口选用及可信区间 | `src/venuegate/gate_backtest/service.py`、`model_choice.py`、`calibration.py` | `tests/test_gate_backtest.py`、`tests/test_model_choice.py`、`tests/test_selection_workbench.py` |
| M6 | 入口偏移 | 差异定位和外推审查 | `src/venuegate/venue_shift/service.py` | `tests/test_venue_shift.py` |
| M7 | 核验分派 | 硬规则与额度分配 | `src/venuegate/usher_capacity/service.py` | `tests/test_usher_capacity.py` |
| M8 | 值班登记 | 单据及额度证据 | `src/venuegate/entrance_register/service.py` | `tests/test_entrance_register.py` |

## 深度登记

| 编号 | 边界 | 判断 | 处理位置 | 测试定位 |
|---|---|---|---|---|
| TRAP-14 | 同版不同读数 | 两条都隔离，换序结论一致 | `src/venuegate/entry_rotations/service.py` | `tests/test_entry_rotations.py::test_conflicting_same_version_is_order_independent` |
| TRAP-19 | 多个规则或外推标记重叠 | 硬约束优先，保留全部命中码 | `src/venuegate/usher_capacity/service.py` | `tests/test_usher_capacity.py::test_hard_rule_precedes_outside_reference` |
| TRAP-23 | 标签落在窗口的终点 | 终点进入隔离段，窗口为半开区间 | `src/venuegate/ticket_windows/service.py` | `tests/test_ticket_windows.py::test_half_open_days` |
| TRAP-32 | 大偏移细方差与常数列 | 中心化后累加，常数列尺度为一 | `src/venuegate/arrival_exposure/service.py` | `tests/test_arrival_exposure.py::test_cancellation_safe_scaling` |
| TRAP-42 | 拟合窗口后才回传结果 | 依标签成熟时间屏蔽，未来数据不参与拟合 | `src/venuegate/ticket_windows/service.py` | `tests/test_ticket_windows.py::test_mature_label_cannot_cross_partition` |
| TRAP-43 | 回放没有成熟记录 | 记录未定义状态，避免以零误差替代 | `src/venuegate/gate_backtest/service.py` | `tests/test_gate_backtest.py::test_no_outcome_gets_undefined_metrics` |
| TRAP-44 | 校准样本不足 | 分派前转人工判读并保留原因 | `src/venuegate/gate_backtest/service.py` | `tests/test_gate_backtest.py::test_empty_calibration_requires_review` |
| TRAP-53 | 单条推断与混批 | 复用冻结参数，各条估计完全一致 | `src/venuegate/visitor_counts/service.py` | `tests/test_visitor_counts.py::test_input_batch_invariance` |
| TRAP-54 | 特征版本与模型不配对 | 拒绝继续推断并要求重拟合 | `src/venuegate/visitor_counts/service.py` | `tests/test_visitor_counts.py::test_mismatched_model_input_version_fails` |
| TRAP-61 | 两套模型比较样本不一致 | 泊松与基线只对同一批成熟实积计算 MAE 与漏报，缺实绩入口直接基线 | `src/venuegate/gate_backtest/model_choice.py` | `tests/test_model_choice.py::test_two_models_always_compare_identical_sample_set` |
| TRAP-62 | 全场 MAE 下降但单入口漏报更多 | 全场资格通过后仍按入口漏报回退基线 | `src/venuegate/gate_backtest/model_choice.py` | `tests/test_model_choice.py::test_entrance_with_more_poisson_misses_falls_back_to_baseline` |
| TRAP-63 | 入口缺同源校准样本 | 不借用其他入口区间，派岗转人工判读 | `src/venuegate/gate_backtest/calibration.py` | `tests/test_model_choice.py::test_missing_calibration_samples_route_to_manual_review` |
| TRAP-64 | 重跑选用结论漂移 | 入口排序与凭证摘要稳定，选用和派岗逐单一致 | `src/venuegate/pipeline.py` | `tests/test_selection_workbench.py::test_rerun_same_batch_keeps_selection_and_dispatch_identical` |
