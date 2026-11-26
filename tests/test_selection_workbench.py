"""工作台层面的入口选用、派岗一致性与重跑确定性。"""

from venuegate.pipeline import execute, model_choice_digest, open_fixture, preview


def test_workbench_reports_which_model_each_entrance_uses_and_why():
    result = preview()
    table = result['model_selection']
    # 首行为全场汇总，之后每个入口一行，附原因和两套模型的回放指标
    assert '全场泊松平均绝对误差' in table[0]
    entrances = {row['入口']: row for row in table[1:]}
    assert entrances, '工作台必须能查各入口选用了哪套'
    live_zones = {row['zone'] for row in result['rows']}
    assert set(entrances) == live_zones
    for row in entrances.values():
        assert row['获准预测'] in {'Poisson 入场人数回归', '预约票兑现率'}
        assert row['选用原因']
        assert '同源校准样本' in row and '校准方式' in row
    # 每条当班单都带选用模型与原因
    for row in result['rows']:
        assert row['forecast_model'] == entrances[row['zone']]['获准预测']
        assert row['selection_reason'] == entrances[row['zone']]['选用原因']


def test_entrance_without_replay_or_calibration_is_baseline_and_manual():
    result = preview()
    unsampled = next(row for row in result['model_selection'][1:]
                     if row['回放成熟实绩'] == 0)
    assert unsampled['获准预测'] == '预约票兑现率'
    assert unsampled['同源校准样本'] == 0
    tickets = [row for row in result['rows'] if row['zone'] == unsampled['入口']]
    assert tickets and all(row['forecast_model'] == '预约票兑现率' for row in tickets)
    # 缺成熟校准样本转人工（无区间），不进入候选派岗
    assert all(row['interval'] == '–' for row in tickets)
    assert all(row['state'] in {'人工判读', '暂停'} for row in tickets)


def test_rerun_same_batch_keeps_selection_and_dispatch_identical():
    dataset = open_fixture()
    first = execute(dataset['records'], 9, 'focus')
    second = execute(list(dataset['records']), 9, 'focus')
    assert first['selection_digest'] == second['selection_digest']
    assert first['run_id'] == second['run_id']
    assert [(row['key'], row['state'], row['forecast_model']) for row in first['rows']] == \
           [(row['key'], row['state'], row['forecast_model']) for row in second['rows']]


def test_selection_digest_changes_when_evidence_changes():
    from venuegate.gate_backtest.contracts import EntranceChoice, SelectionBoard
    base = SelectionBoard(
        (EntranceChoice('甲入口', '预约票兑现率', '原因', 5, 1.0, 2.0, 0, 1, 155.0, 3, 'm'),),
        1.0, 2.0, 5, False)
    swapped = SelectionBoard(
        (EntranceChoice('甲入口', 'Poisson 入场人数回归', '另一原因', 5, 1.0, 2.0, 0, 1, 155.0, 3, 'm'),),
        1.0, 2.0, 5, True)
    assert model_choice_digest(base) != model_choice_digest(swapped)


def test_replay_stage_carries_selection_evidence():
    result = preview()
    stage = next(section for section in result['sections'] if section['key'] == 'gate_backtest')
    assert any('获准预测' in record for record in stage['records'])
    assert any('选用原因' in record for record in stage['records'])


def test_late_reported_live_outcome_does_not_change_frozen_selection():
    dataset = open_fixture()
    entries = [dict(row) for row in dataset['records']]
    contact = next(row for row in entries if row['day'] == 88)
    contact['result_day'] = 94
    contact['outcome'] = 1
    before = preview()
    after = execute(entries)
    assert after['selection_digest'] == before['selection_digest']
    assert after['rows'] == before['rows']
