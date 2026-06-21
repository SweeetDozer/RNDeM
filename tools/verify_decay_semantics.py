from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clc.action.action_candidate import ActionCandidate
from clc.action.action_candidate_field import ActionCandidateField
from clc.core.ids import IdGenerator
from clc.field.active_context_field import ActiveContextField
from clc.field.active_pattern import ActivePattern


PATTERN_ID = "pat_decay_probe"
ACTION_ID = "pat_action_decay_probe"
DECAY_RATE = 0.1
TICKS = (1, 2, 3, 4, 5)


@dataclass
class TraceRow:
    tick: int
    before: float | None
    after: float | None
    updated_before: int | None
    updated_after: int | None
    last_decay_before: int | None
    last_decay_after: int | None
    elapsed_used: int | None
    present_after: bool


def main() -> int:
    active_no_reinforcement = _active_no_reinforcement_trace()
    active_reinforcement = _active_reinforcement_trace()
    candidate_no_reinforcement = _candidate_no_reinforcement_trace()
    candidate_reinforcement = _candidate_reinforcement_trace()

    active_classification = _classify_trace(active_no_reinforcement, 1.0, 0, DECAY_RATE)
    candidate_classification = _classify_trace(candidate_no_reinforcement, 1.0, 0, DECAY_RATE)

    print("ActiveContextField decay trace:")
    _print_trace(active_no_reinforcement)
    print("ActiveContextField reinforcement trace:")
    _print_trace(active_reinforcement)
    print("ActionCandidateField decay trace:")
    _print_trace(candidate_no_reinforcement)
    print("ActionCandidateField reinforcement trace:")
    _print_trace(candidate_reinforcement)
    print("Decay model classification:")
    print(f"  ActiveContextField appears closest to: {active_classification}")
    print(f"  ActionCandidateField appears closest to: {candidate_classification}")

    checks = {
        "active trace produced": bool(active_no_reinforcement),
        "candidate trace produced": bool(candidate_no_reinforcement),
        "active classification stepwise": active_classification == "stepwise",
        "candidate classification stepwise": candidate_classification == "stepwise",
        "active expected stepwise trace": _matches_expected_after(active_no_reinforcement, [0.9, 0.8, 0.7, 0.6, 0.5]),
        "candidate expected stepwise trace": _matches_expected_after(candidate_no_reinforcement, [0.9, 0.8, 0.7, 0.6, 0.5]),
        "active old repeated-elapsed gone": not _matches_expected_after(active_no_reinforcement[:3], [0.9, 0.7, 0.4]),
        "candidate old repeated-elapsed gone": not _matches_expected_after(candidate_no_reinforcement[:3], [0.9, 0.7, 0.4]),
        "active updated_at stable during decay": _updated_at_stable_during_decay(active_no_reinforcement, expected=0),
        "candidate updated_at stable during decay": _updated_at_stable_during_decay(candidate_no_reinforcement, expected=0),
        "active last_decay moves during decay": _last_decay_moves_stepwise(active_no_reinforcement),
        "candidate last_decay moves during decay": _last_decay_moves_stepwise(candidate_no_reinforcement),
        "active reinforcement updates timestamp": _has_updated_at_after_reinforcement(active_reinforcement, expected=3),
        "candidate reinforcement updates timestamp": _has_updated_at_after_reinforcement(candidate_reinforcement, expected=3),
        "active reinforcement resets last_decay": _has_last_decay_after_reinforcement(active_reinforcement, expected=3),
        "candidate reinforcement resets last_decay": _has_last_decay_after_reinforcement(candidate_reinforcement, expected=3),
        "activation values valid": _values_valid(active_no_reinforcement + active_reinforcement + candidate_no_reinforcement + candidate_reinforcement),
    }
    print("Decay semantics verification:")
    for name, ok in checks.items():
        print(f"  {name}: {'yes' if ok else 'no'}")
    passed = all(checks.values())
    print(f"  result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def _active_no_reinforcement_trace() -> list[TraceRow]:
    field = ActiveContextField()
    field.activate(PATTERN_ID, 1.0, 0, "diagnostic", decay_rate=DECAY_RATE, ttl=None)
    return [_decay_active(field, tick, PATTERN_ID) for tick in TICKS]


def _active_reinforcement_trace() -> list[TraceRow]:
    field = ActiveContextField()
    field.activate(PATTERN_ID, 1.0, 0, "diagnostic", decay_rate=DECAY_RATE, ttl=None)
    rows = [_decay_active(field, 1, PATTERN_ID), _decay_active(field, 2, PATTERN_ID)]
    before = _active_entry(field, PATTERN_ID)
    field.activate(PATTERN_ID, 0.5, 3, "diagnostic", decay_rate=DECAY_RATE, ttl=None)
    after = _active_entry(field, PATTERN_ID)
    rows.append(
        TraceRow(
            tick=3,
            before=before.activation if before else None,
            after=after.activation if after else None,
            updated_before=before.updated_at_tick if before else None,
            updated_after=after.updated_at_tick if after else None,
            last_decay_before=before.last_decay_tick if before else None,
            last_decay_after=after.last_decay_tick if after else None,
            elapsed_used=None,
            present_after=after is not None,
        )
    )
    rows.extend([_decay_active(field, 4, PATTERN_ID), _decay_active(field, 5, PATTERN_ID)])
    return rows


def _candidate_no_reinforcement_trace() -> list[TraceRow]:
    field = ActionCandidateField(IdGenerator())
    field.propose(ACTION_ID, 1.0, 0, decay_rate=DECAY_RATE, ttl=None)
    return [_decay_candidate(field, tick, ACTION_ID) for tick in TICKS]


def _candidate_reinforcement_trace() -> list[TraceRow]:
    field = ActionCandidateField(IdGenerator())
    field.propose(ACTION_ID, 1.0, 0, decay_rate=DECAY_RATE, ttl=None)
    rows = [_decay_candidate(field, 1, ACTION_ID), _decay_candidate(field, 2, ACTION_ID)]
    before = _candidate_entry(field, ACTION_ID)
    field.propose(ACTION_ID, 0.5, 3, decay_rate=DECAY_RATE, ttl=None)
    after = _candidate_entry(field, ACTION_ID)
    rows.append(
        TraceRow(
            tick=3,
            before=before.activation if before else None,
            after=after.activation if after else None,
            updated_before=before.updated_at_tick if before else None,
            updated_after=after.updated_at_tick if after else None,
            last_decay_before=before.last_decay_tick if before else None,
            last_decay_after=after.last_decay_tick if after else None,
            elapsed_used=None,
            present_after=after is not None,
        )
    )
    rows.extend([_decay_candidate(field, 4, ACTION_ID), _decay_candidate(field, 5, ACTION_ID)])
    return rows


def _decay_active(field: ActiveContextField, tick: int, pattern_id: str) -> TraceRow:
    before = _active_entry(field, pattern_id)
    field.decay_all(tick)
    after = _active_entry(field, pattern_id)
    return TraceRow(
        tick=tick,
        before=before.activation if before else None,
        after=after.activation if after else None,
        updated_before=before.updated_at_tick if before else None,
        updated_after=after.updated_at_tick if after else None,
        last_decay_before=before.last_decay_tick if before else None,
        last_decay_after=after.last_decay_tick if after else None,
        elapsed_used=max(0, tick - (before.last_decay_tick if before.last_decay_tick is not None else before.updated_at_tick)) if before else None,
        present_after=after is not None,
    )


def _decay_candidate(field: ActionCandidateField, tick: int, pattern_id: str) -> TraceRow:
    before = _candidate_entry(field, pattern_id)
    field.decay_all(tick)
    after = _candidate_entry(field, pattern_id)
    return TraceRow(
        tick=tick,
        before=before.activation if before else None,
        after=after.activation if after else None,
        updated_before=before.updated_at_tick if before else None,
        updated_after=after.updated_at_tick if after else None,
        last_decay_before=before.last_decay_tick if before else None,
        last_decay_after=after.last_decay_tick if after else None,
        elapsed_used=max(0, tick - (before.last_decay_tick if before.last_decay_tick is not None else before.updated_at_tick)) if before else None,
        present_after=after is not None,
    )


def _active_entry(field: ActiveContextField, pattern_id: str) -> ActivePattern | None:
    return field._patterns.get(pattern_id)


def _candidate_entry(field: ActionCandidateField, pattern_id: str) -> ActionCandidate | None:
    return next((candidate for candidate in field._candidates.values() if candidate.pattern_id == pattern_id), None)


def _classify_trace(trace: list[TraceRow], initial_activation: float, updated_at_tick: int, decay_rate: float) -> str:
    observed = {row.tick: row.after for row in trace if row.after is not None}
    if not observed:
        return "unknown"
    last_reinforcement = {
        tick: model_decay_from_last_reinforcement(initial_activation, tick, updated_at_tick, decay_rate)
        for tick in observed
    }
    stepwise = model_stepwise_decay(initial_activation, observed.keys(), decay_rate)
    repeated_elapsed = model_repeated_elapsed_subtraction(initial_activation, observed.keys(), updated_at_tick, decay_rate)
    if _matches_model(observed, stepwise) and _last_decay_moves_stepwise(trace):
        return "stepwise"
    if _matches_model(observed, repeated_elapsed):
        return "mixed/repeated_elapsed_subtraction"
    if _matches_model(observed, last_reinforcement):
        return "from_last_reinforcement"
    return "mixed"


def model_decay_from_last_reinforcement(initial_activation: float, tick: int, updated_at_tick: int, decay_rate: float) -> float:
    elapsed = max(0, tick - updated_at_tick)
    return _clamp(initial_activation - decay_rate * elapsed)


def model_stepwise_decay(initial_activation: float, ticks: object, decay_rate: float) -> dict[int, float]:
    activation = initial_activation
    values: dict[int, float] = {}
    previous_tick = 0
    for tick in sorted(int(item) for item in ticks):
        elapsed = max(0, tick - previous_tick)
        activation = _clamp(activation - decay_rate * elapsed)
        values[tick] = activation
        previous_tick = tick
    return values


def model_repeated_elapsed_subtraction(
    initial_activation: float,
    ticks: object,
    updated_at_tick: int,
    decay_rate: float,
) -> dict[int, float]:
    activation = initial_activation
    values: dict[int, float] = {}
    for tick in sorted(int(item) for item in ticks):
        elapsed = max(0, tick - updated_at_tick)
        activation = _clamp(activation - decay_rate * elapsed)
        if activation <= 0.01:
            break
        values[tick] = activation
    return values


def _matches_model(observed: dict[int, float | None], model: dict[int, float]) -> bool:
    return all(tick in model and math.isclose(float(value), model[tick], abs_tol=1e-9) for tick, value in observed.items())


def _updated_at_stable_during_decay(trace: list[TraceRow], expected: int) -> bool:
    decay_rows = [row for row in trace if row.elapsed_used is not None and row.updated_before is not None]
    return bool(decay_rows) and all(row.updated_before == expected and row.updated_after == expected for row in decay_rows if row.present_after)


def _has_updated_at_after_reinforcement(trace: list[TraceRow], expected: int) -> bool:
    return any(row.tick == expected and row.elapsed_used is None and row.updated_after == expected for row in trace)


def _has_last_decay_after_reinforcement(trace: list[TraceRow], expected: int) -> bool:
    return any(row.tick == expected and row.elapsed_used is None and row.last_decay_after == expected for row in trace)


def _last_decay_moves_stepwise(trace: list[TraceRow]) -> bool:
    decay_rows = [row for row in trace if row.elapsed_used is not None and row.present_after]
    return bool(decay_rows) and all(row.last_decay_after == row.tick for row in decay_rows)


def _matches_expected_after(trace: list[TraceRow], expected: list[float]) -> bool:
    if len(trace) < len(expected):
        return False
    for row, value in zip(trace, expected):
        if row.after is None or not math.isclose(row.after, value, abs_tol=1e-9):
            return False
    return True


def _values_valid(trace: list[TraceRow]) -> bool:
    for row in trace:
        for value in (row.before, row.after):
            if value is not None and not 0.0 <= value <= 1.0:
                return False
    return True


def _print_trace(trace: list[TraceRow]) -> None:
    for row in trace:
        before = "missing" if row.before is None else f"{row.before:.3f}"
        after = "removed" if row.after is None else f"{row.after:.3f}"
        print(
            f"  tick={row.tick} before={before} after={after} "
            f"updated_at {row.updated_before}->{row.updated_after} "
            f"last_decay {row.last_decay_before}->{row.last_decay_after} "
            f"elapsed_used={row.elapsed_used}"
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


if __name__ == "__main__":
    raise SystemExit(main())
