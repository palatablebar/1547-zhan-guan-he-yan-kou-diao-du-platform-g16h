"""入口回放选用与同源校准的回归测试。

每个分支都用可复算的合成数据固定触发，避免依赖样例数据的偶然形状。
"""

import pytest

from venuegate.arrival_exposure.contracts import FeatureVector
from venuegate.gate_backtest import model_choice
from venuegate.gate_backtest.calibration import (
    assess_live,
    baseline_prediction,
    build_entrance_calibrations,
)
from venuegate.gate_backtest.contracts import BASELINE_MODEL, POISSON_MODEL, SelectionBoard
from venuegate.visitor_counts.service import fit_model

STAMP = 'test-feature-stamp'
THRESHOLD = 155.0
FLAT_FEATURES = (0.1, -0.2, 0.3, 0.0, 0.1)


def vector(key, cohort, day, outcome, vals=FLAT_FEATURES, res=200.0, *, observed=True):
    raw = (res, 10.0, 5.0, 8.0, 30.0, 25.0)
    return FeatureVector(key, cohort, day, vals, (), (), (), outcome, observed, raw)


@pytest.fixture(scope='module')
def feature_driven_fit():
    # 实绩随缩放特征线性变化、预约票量固定：泊松能学到关系，基线退化为常数
    train = tuple(vector(f'T-{i:02d}', '甲入口', i + 1, 100 + 20 * i,
                         (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(16))
    return fit_model(train, STAMP), train


def test_global_mae_drop_enables_poisson_when_misses_not_worse(feature_driven_fit):
    fit, train = feature_driven_fit
    replay = tuple(vector(f'J{i}', '甲入口', 70 + i, 100 + 20 * i + (8 if i % 2 else -8),
                          (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(6))
    board = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    choice = board.for_cohort('甲入口')
    assert board.poisson_preferred is True
    assert choice.chosen == POISSON_MODEL
    assert choice.reason == model_choice.REASON_POISSON
    assert choice.poisson_mae < choice.baseline_mae
    assert choice.replay_count == 6


def test_global_mae_without_drop_keeps_baseline_everywhere():
    # 回放实绩与预约票量都恒定：基线零误差，正则化泊松留有残差，全局 MAE 不下降
    train = tuple(vector(f'T{i}', '甲入口', i + 1, 130.0 + (i % 2) * 10.0,
                         (0.05 * i, 0.0, 0.0, 0.0, 0.0), res=180.0) for i in range(16))
    fit = fit_model(train, STAMP)
    replay = tuple(vector(f'R{i}', '甲入口', 70 + i, 135.0,
                          (0.4 + 0.08 * i, 0.0, 0.0, 0.0, 0.0), res=180.0) for i in range(6))
    board = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    assert board.poisson_preferred is False
    choice = board.for_cohort('甲入口')
    assert choice.chosen == BASELINE_MODEL
    assert choice.reason == model_choice.REASON_GLOBAL
    assert choice.poisson_mae >= choice.baseline_mae


def test_entrance_with_more_poisson_misses_falls_back_to_baseline(feature_driven_fit):
    fit, train = feature_driven_fit
    # 甲入口让全局泊松占优；乙入口特征固定（泊松近似常数），半数实绩跳到阈值上，
    # 而这些批次预约票量高，基线能够预警，泊松漏报严格多于基线
    jia = tuple(vector(f'J{i}', '甲入口', 70 + i, 100 + 20 * i + (8 if i % 2 else -8),
                       (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(6))
    yi = tuple(vector(f'Y{i}', '乙入口', 70 + i, 130.0 if i % 2 == 0 else 175.0,
                      FLAT_FEATURES, res=150.0 if i % 2 == 0 else 260.0) for i in range(6))
    board = model_choice.choose_entrance_models(fit, STAMP, jia + yi, train, threshold=THRESHOLD)
    assert board.poisson_preferred is True
    assert board.for_cohort('甲入口').chosen == POISSON_MODEL
    yi_choice = board.for_cohort('乙入口')
    assert yi_choice.chosen == BASELINE_MODEL
    assert yi_choice.reason == model_choice.REASON_MISSES
    assert yi_choice.poisson_missed > yi_choice.baseline_missed


def test_entrance_without_mature_replay_uses_baseline(feature_driven_fit):
    fit, train = feature_driven_fit
    replay = (vector('OPEN-1', '新入口', 70, None),)
    board = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    board = model_choice.register_unsampled_entrances(board, replay, threshold=THRESHOLD)
    choice = board.for_cohort('新入口')
    assert choice.chosen == BASELINE_MODEL
    assert choice.reason == model_choice.REASON_NO_REPLAY
    assert choice.replay_count == 0 and choice.poisson_mae is None


def test_censored_and_missing_samples_are_not_mature(feature_driven_fit):
    fit, train = feature_driven_fit
    replay = (
        vector('C-1', '丁入口', 70, 0.0, observed=False),
        vector('C-2', '丁入口', 71, None),
    )
    board = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    board = model_choice.register_unsampled_entrances(board, replay, threshold=THRESHOLD)
    assert board.for_cohort('丁入口').chosen == BASELINE_MODEL
    assert board.global_replay_count == 0 and board.poisson_preferred is False


def test_two_models_always_compare_identical_sample_set(feature_driven_fit):
    fit, train = feature_driven_fit
    replay = tuple(vector(f'J{i}', '甲入口', 70 + i, 100 + 20 * i,
                          (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(4))
    board = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    choice = board.for_cohort('甲入口')
    assert choice.replay_count == len(replay)
    assert 0 <= choice.poisson_missed <= choice.replay_count
    assert 0 <= choice.baseline_missed <= choice.replay_count


def test_missing_calibration_samples_route_to_manual_review(feature_driven_fit):
    fit, train = feature_driven_fit
    live = (vector('L-1', '新入口', 90, None, res=210.0),)
    board = model_choice.register_unsampled_entrances(
        SelectionBoard((), None, None, 0, False), live, threshold=THRESHOLD)
    board, verifications, conversion = build_entrance_calibrations(
        board, fit, STAMP, train, ())
    checked = assess_live(board, verifications, fit, STAMP, conversion, live)
    assert len(checked) == 1
    assert checked[0].uncertain is True and checked[0].upper is None
    assert board.for_cohort('新入口').calibration_size == 0


def test_same_source_calibration_uses_only_the_entrance_own_samples(feature_driven_fit):
    fit, train = feature_driven_fit
    calibration = tuple(vector(f'K{i}', '甲入口', 50 + i, 118.0 + 4 * i,
                               (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(4))
    board = model_choice.choose_entrance_models(
        fit, STAMP, calibration, train, threshold=THRESHOLD)
    board, verifications, conversion = build_entrance_calibrations(
        board, fit, STAMP, train, calibration)
    choice = board.for_cohort('甲入口')
    assert choice.calibration_size == 4
    assert verifications['甲入口'].size == 4
    live = (vector('L-9', '甲入口', 90, None, res=205.0),)
    checked = assess_live(board, verifications, fit, STAMP, conversion, live)
    assert checked[0].raw.key == 'L-9'
    assert checked[0].lower is not None and checked[0].upper >= checked[0].lower


def test_baseline_prediction_matches_frozen_fulfilment_rate(feature_driven_fit):
    _, train = feature_driven_fit
    conversion = sum(r.outcome for r in train) / sum(r.input_values[0] for r in train)
    row = vector('B-1', '甲入口', 90, None, res=240.0)
    pred = baseline_prediction(conversion, row)
    assert pred.score == max(.01, conversion * 240.0)
    assert pred.key == row.key and pred.cohort == row.cohort


def test_selection_is_order_independent(feature_driven_fit):
    fit, train = feature_driven_fit
    replay = (
        *(vector(f'J{i}', '甲入口', 70 + i, 100 + 20 * i,
                 (0.05 * i, 0.0, 0.0, 0.0, 0.0)) for i in range(4)),
        *(vector(f'Y{i}', '乙入口', 70 + i, 130.0 if i % 2 == 0 else 175.0,
                 FLAT_FEATURES, res=150.0 if i % 2 == 0 else 260.0) for i in range(4)),
    )
    first = model_choice.choose_entrance_models(fit, STAMP, replay, train, threshold=THRESHOLD)
    second = model_choice.choose_entrance_models(
        fit, STAMP, tuple(reversed(replay)), train, threshold=THRESHOLD)
    assert first.evidence() == second.evidence()
    assert first.poisson_preferred == second.poisson_preferred
