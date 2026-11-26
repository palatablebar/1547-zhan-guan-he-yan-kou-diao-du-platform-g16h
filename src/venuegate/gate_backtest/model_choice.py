"""入口回放选用：泊松回归与预约兑现率基线只在同一批成熟实绩上比较。

迟到补报的样本在分窗阶段已按成熟时间屏蔽，不会进入这里；因此本模块
只处理回放窗内 ``outcome`` 已知且未右截尾的成熟实绩。
"""

from collections import defaultdict
from math import fabs, fsum

from ..visitor_counts.baseline import apparent_arrivals, attendance_conversion
from ..visitor_counts.service import predict as poisson_predict
from .contracts import BASELINE_MODEL, EntranceChoice, POISSON_MODEL, SelectionBoard

REASON_NO_REPLAY = '入口无回放实绩，沿用预约兑现率基线'
REASON_MISSES = '泊松漏报越线批数多于基线，回退基线'
REASON_GLOBAL = '全场回放平均绝对误差未下降，沿用基线'
REASON_POISSON = '全场平均绝对误差下降且本入口漏报不劣于基线，获准泊松回归'
REASON_TIE = '泊松与基线回放误差持平，沿用基线'


def baseline_score(conversion, vector):
    """预约兑现率基线：训练窗冻结的兑现率 × 本批预约票量。"""
    return apparent_arrivals(conversion, vector)


def _mature(vectors):
    return tuple(row for row in vectors if row.outcome is not None and row.observed)


def _metrics(pairs, threshold):
    """pairs 内每条为 (预测, 实绩)，两套模型使用完全相同的样本。"""
    count = len(pairs)
    if not count:
        return 0, None, 0
    mae = fsum(fabs(score - outcome) for score, outcome in pairs) / count
    missed = sum(score < threshold <= outcome for score, outcome in pairs)
    return count, mae, missed


def choose_entrance_models(fit, feature_stamp, replay_vectors, training_vectors,
                           *, threshold=155.0):
    """决定当班各入口获准使用哪套客流预测。

    全场回放平均绝对误差下降时泊松回归才具备候选资格；漏报越线批次比
    预约兑现率基线多的入口仍回退基线；没有成熟回放实绩的入口直接用基线。
    """
    mature = _mature(replay_vectors)
    conversion = attendance_conversion(training_vectors)
    poisson_scores = {row.key: row.score for row in poisson_predict(fit, mature, feature_stamp)}

    by_cohort = defaultdict(list)
    for row in mature:
        by_cohort[row.cohort].append(
            (row, poisson_scores[row.key], baseline_score(conversion, row)))

    global_poisson = [(poisson, row.outcome) for row, poisson, _ in (
        item for cases in by_cohort.values() for item in cases)]
    global_count, global_poisson_mae, _ = _metrics(global_poisson, threshold)
    global_baseline = [(base, row.outcome) for row, _, base in (
        item for cases in by_cohort.values() for item in cases)]
    _, global_baseline_mae, _ = _metrics(global_baseline, threshold)

    if global_count and global_poisson_mae < global_baseline_mae:
        poisson_preferred = True
    else:
        # 无回放实绩或误差未严格下降（含持平）时，全场不启用泊松
        poisson_preferred = False

    choices = []
    for cohort in sorted(by_cohort):
        cases = by_cohort[cohort]
        p_count, p_mae, p_missed = _metrics(
            [(poisson, row.outcome) for row, poisson, _ in cases], threshold)
        b_count, b_mae, b_missed = _metrics(
            [(base, row.outcome) for row, _, base in cases], threshold)
        if p_count != b_count:
            raise ArithmeticError('两套模型必须比较同一批成熟实绩')
        if not poisson_preferred:
            chosen, reason = BASELINE_MODEL, (
                REASON_TIE if global_count and global_poisson_mae == global_baseline_mae
                else REASON_GLOBAL)
        elif p_missed > b_missed:
            chosen, reason = BASELINE_MODEL, REASON_MISSES
        else:
            chosen, reason = POISSON_MODEL, REASON_POISSON
        choices.append(EntranceChoice(cohort, chosen, reason, p_count,
                                      p_mae, b_mae, p_missed, b_missed, threshold))

    choices = tuple(sorted(choices, key=lambda item: item.cohort))
    return SelectionBoard(choices, global_poisson_mae, global_baseline_mae,
                          global_count, poisson_preferred)


def register_unsampled_entrances(board, vectors, *, threshold=155.0):
    """没有任何成熟回放实绩的入口（含当班才出现的未知作业区）强制基线。"""
    extra = []
    present = {choice.cohort for choice in board.choices}
    for row in vectors:
        if row.cohort not in present:
            present.add(row.cohort)
            extra.append(EntranceChoice(row.cohort, BASELINE_MODEL, REASON_NO_REPLAY,
                                        0, None, None, 0, 0, threshold))
    if not extra:
        return board
    return SelectionBoard(tuple(sorted((*board.choices, *extra), key=lambda item: item.cohort)),
                          board.global_poisson_mae, board.global_baseline_mae,
                          board.global_replay_count, board.poisson_preferred)


def selection_evidence(board):
    header = [{'全场回放成熟实绩': board.global_replay_count,
               '全场泊松平均绝对误差':
                   None if board.global_poisson_mae is None else round(board.global_poisson_mae, 4),
               '全场基线平均绝对误差':
                   None if board.global_baseline_mae is None else round(board.global_baseline_mae, 4),
               '泊松全场获准': '是' if board.poisson_preferred else '否'}]
    return header + board.evidence()
