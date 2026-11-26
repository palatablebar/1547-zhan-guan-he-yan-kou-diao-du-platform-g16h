# ENTRY / SHIFT运行手册

更换班次或复算派单时使用。先确认 `/health` 返回 `ok`，再检查以下入口和凭证中的 `run_id`。

| 文档或路由 | 用途 |
|---|---|
| `sample_data/entry_rotations_sample.json` | 同时提供拟合、校准、回放和当班的样例 |
| `GET /api/venuegate/overview` | 默认额度和样例处置 |
| `POST /api/venuegate/run` | 用 `capacity` 和 `strategy` 调整派单，也可同时提供 `records` 与 `as_of` |
| `GET /api/venuegate/stages/<环节>` | 样例的分环节核对，可传相同额度、策略 |

导入 JSON 对象时 `records` 为 1–2500 条单据，`as_of` 为整数工日；默认第 96 日。额度接受 1–60，策略接受 `balanced` 或 `focus`。入站异常保留于第一环节。整批缺少成熟窗口时响应 422 并给出原因。

```sh
docker compose exec -T app python -m venuegate.entry evaluate --input sample_data/entry_rotations_sample.json --capacity 9
```

在网页筛选单号、作业区或原因，点击结果中的单号查看完整字段与处置证据。下载 JSON 可检视结果、对照原始资料摘要和模型特征版本。

## 入口选用核对

`GET /api/venuegate/stages/gate_backtest` 和总览返回的 `model_selection` 列出每个入口获准的预测模型、选用原因、两套模型在同一批成熟回放实绩上的平均绝对误差与越线漏报批数，以及同源校准样本数。总览的 `selection_digest` 是选用结论摘要，已计入批次凭证：同一批单据重跑时摘要、`run_id` 和派岗逐单一致。每条当班单的 `forecast_model` 与 `selection_reason` 显示该单实际采用的模型；区间显示为 `–` 表示该入口缺成熟校准样本，已转人工判读。
