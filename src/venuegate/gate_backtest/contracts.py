from dataclasses import dataclass
from ..visitor_counts.contracts import Prediction

RISK_MODE = False

POISSON_MODEL = 'Poisson 入场人数回归'
BASELINE_MODEL = '预约票兑现率'
# 入口选用结果的稳定顺序，保证重跑同一批输出一致
MODEL_CHOICES = (POISSON_MODEL, BASELINE_MODEL)


@dataclass(frozen=True, slots=True)
class EntranceChoice:
    """单个入口在本班回放中被获准的预测模型及其依据。"""

    cohort: str
    chosen: str
    reason: str
    replay_count: int
    poisson_mae: float | None
    baseline_mae: float | None
    poisson_missed: int
    baseline_missed: int
    threshold: float
    calibration_size: int = 0
    calibration_method: str | None = None

    def __post_init__(self):
        if self.chosen not in MODEL_CHOICES:
            raise ValueError('获准预测必须来自两套候选模型')
        if self.replay_count < 0 or self.calibration_size < 0:
            raise ValueError('回放与校准样本数不可为负')
        if self.poisson_missed < 0 or self.baseline_missed < 0:
            raise ValueError('漏报批数不可为负')

    def evidence(self):
        return {'入口': self.cohort, '获准预测': self.chosen, '选用原因': self.reason,
                '回放成熟实绩': self.replay_count,
                '泊松平均绝对误差': None if self.poisson_mae is None else round(self.poisson_mae, 4),
                '基线平均绝对误差': None if self.baseline_mae is None else round(self.baseline_mae, 4),
                '泊松漏报越线批数': self.poisson_missed, '基线漏报越线批数': self.baseline_missed,
                '越线阈值': self.threshold, '同源校准样本': self.calibration_size,
                '校准方式': self.calibration_method or '—'}


@dataclass(frozen=True, slots=True)
class SelectionBoard:
    """全场入口的选用登记，重跑同一批必须得到完全一致的结论。"""

    choices: tuple[EntranceChoice, ...]
    global_poisson_mae: float | None
    global_baseline_mae: float | None
    global_replay_count: int
    poisson_preferred: bool

    def __post_init__(self):
        cohorts = [choice.cohort for choice in self.choices]
        if len(cohorts) != len(set(cohorts)):
            raise ValueError('每个入口只能登记一条选用记录')
        if not self.choices and self.global_replay_count:
            raise ValueError('存在回放实绩却没有入口选用记录')

    def for_cohort(self, cohort):
        for choice in self.choices:
            if choice.cohort == cohort:
                return choice
        return None

    def chosen_model(self, cohort):
        choice = self.for_cohort(cohort)
        return choice.chosen if choice is not None else BASELINE_MODEL

    def evidence(self):
        return [choice.evidence() for choice in self.choices]


@dataclass(frozen=True, slots=True)
class Verification:
    method: str
    parameters: tuple
    size: int
    positives: int | None

    def __post_init__(self):
        if self.size < 0 or self.positives is not None and not 0 <= self.positives <= self.size:
            raise ValueError('校准回查计数失衡')


@dataclass(frozen=True, slots=True)
class Assessment:
    raw: Prediction
    estimate: float
    lower: float | None
    upper: float | None
    uncertain: bool


@dataclass(frozen=True, slots=True)
class CalibrationRow:
    index: int
    predicted: float | None
    observed: float | None
    count: int


@dataclass(frozen=True, slots=True)
class ModelReport:
    status: str
    count: int
    mae: float | None
    error: float | None
    buckets: tuple[CalibrationRow, ...]
    auxiliary: int | float | None
