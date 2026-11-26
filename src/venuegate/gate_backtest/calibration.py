"""派岗前的同源校准：每个入口只采用获准模型在该入口成熟校准样本上的区间。

缺少成熟校准样本的入口不构造区间，派岗环节按既有 INSUFFICIENT_CALIBRATION
规则转人工判读。
"""

from dataclasses import replace

from ..visitor_counts.baseline import apparent_arrivals, attendance_conversion
from ..visitor_counts.contracts import Prediction
from ..visitor_counts.service import predict as poisson_predict
from .contracts import BASELINE_MODEL, POISSON_MODEL
from .service import check_point, prepare_verification


def baseline_prediction(conversion, vector):
    """把基线估计包装成与泊松输出同构的 Prediction，复用同一套区间校验。"""
    return Prediction(vector.key, vector.cohort, vector.day,
                      apparent_arrivals(conversion, vector), (), vector.missing,
                      vector.excursions, vector.outcome, vector.observed,
                      vector.input_values)


def score_vectors(chosen, fit, feature_stamp, conversion, vectors):
    if chosen == POISSON_MODEL:
        return poisson_predict(fit, vectors, feature_stamp)
    if chosen == BASELINE_MODEL:
        return tuple(baseline_prediction(conversion, row) for row in vectors)
    raise ValueError('未知的获准预测模型')


def calibrate_entrance(choice, fit, feature_stamp, conversion, calibration_vectors,
                       *, coverage=.85):
    """在入口自己的成熟校准样本上拟合获准模型的区间参数。"""
    rows = tuple(row for row in calibration_vectors
                 if row.cohort == choice.cohort and row.outcome is not None and row.observed)
    if not rows:
        return replace(choice, calibration_size=0, calibration_method=None), \
            prepare_verification(())
    scored = score_vectors(choice.chosen, fit, feature_stamp, conversion, rows)
    verification = prepare_verification(scored, coverage=coverage)
    return (replace(choice, calibration_size=verification.size,
                    calibration_method=verification.method), verification)


def build_entrance_calibrations(board, fit, feature_stamp, training_vectors,
                                calibration_vectors, *, coverage=.85):
    """返回 (补登校准信息的 SelectionBoard, 入口 -> Verification)。"""
    conversion = attendance_conversion(training_vectors)
    choices = []
    verifications = {}
    for choice in board.choices:
        updated, verification = calibrate_entrance(
            choice, fit, feature_stamp, conversion, calibration_vectors, coverage=coverage)
        choices.append(updated)
        verifications[choice.cohort] = verification
    updated_board = replace(board, choices=tuple(choices))
    return updated_board, verifications, conversion


def assess_live(board, verifications, fit, feature_stamp, conversion, live_vectors):
    """按每个入口获准的模型打分，并套上该入口的同源校准区间。"""
    grouped = {}
    for row in live_vectors:
        grouped.setdefault(row.cohort, []).append(row)
    assessments = []
    for cohort in sorted(grouped):
        rows = tuple(grouped[cohort])
        choice = board.for_cohort(cohort)
        chosen = choice.chosen if choice is not None else BASELINE_MODEL
        scored = score_vectors(chosen, fit, feature_stamp, conversion, rows)
        verification = verifications.get(cohort, prepare_verification(()))
        assessments.extend(check_point(record, verification) for record in scored)
    order = {row.key: index for index, row in enumerate(live_vectors)}
    return tuple(sorted(assessments, key=lambda view: order[view.raw.key]))
