# Decay Semantics Audit

This note documents observed behavior only. It does not decide whether the behavior should change.

## ActiveContextField

Observed with activation `1.0`, `decay_rate=0.1`, `updated_at_tick=0`, no reinforcement:

```text
tick=1 before=1.000 after=0.900 updated_at 0->0 elapsed_used=1
tick=2 before=0.900 after=0.700 updated_at 0->0 elapsed_used=2
tick=3 before=0.700 after=0.400 updated_at 0->0 elapsed_used=3
tick=4 before=0.400 after=removed updated_at 0->None elapsed_used=4
tick=5 before=missing after=removed updated_at None->None elapsed_used=None
```

`updated_at_tick` remains stable during decay. Reinforcement/update changes `updated_at_tick` to the reinforcement tick and subsequent decay uses that new timestamp.

## ActionCandidateField

Observed behavior matches `ActiveContextField` for the same activation, timestamp, and decay rate:

```text
tick=1 before=1.000 after=0.900 updated_at 0->0 elapsed_used=1
tick=2 before=0.900 after=0.700 updated_at 0->0 elapsed_used=2
tick=3 before=0.700 after=0.400 updated_at 0->0 elapsed_used=3
tick=4 before=0.400 after=removed updated_at 0->None elapsed_used=4
tick=5 before=missing after=removed updated_at None->None elapsed_used=None
```

`updated_at_tick` remains stable during decay. Reinforcement/update changes `updated_at_tick` to the reinforcement tick.

## Interpretation

Current behavior is neither ordinary stepwise decay nor direct decay from the original activation. It is best described as repeated elapsed subtraction:

```text
activation = current_activation - decay_rate * (tick - updated_at_tick)
```

Because `current_activation` is mutated on each decay while `updated_at_tick` remains unchanged, the elapsed penalty grows on each tick until the item is reinforced or removed.

## Future Decision

The behavior may be intentional as an aggressive fading model from last reinforcement, but it is operationally ambiguous. A future architecture pass should explicitly choose one of:

- keep current repeated-elapsed behavior and document it as intentional;
- change to stepwise decay;
- split decay policy by field type;
- make decay policy configurable per field or activation source.

## Normalized Behavior

The previous behavior was repeated-elapsed subtraction:

```text
activation = current_activation - decay_rate * (tick - updated_at_tick)
```

Because `updated_at_tick` did not move during decay, each decay pass subtracted an increasingly large elapsed penalty from an already-decayed activation.

The normalized behavior is stepwise decay:

```text
activation = current_activation - decay_rate * (tick - last_decay_tick)
```

`updated_at_tick` now means the last real update/reinforcement tick. It is not changed by decay.

`last_decay_tick` means the last tick where decay was accounted for. It moves when decay is applied, and it is reset to the current tick when an entry is created or reinforced.

Observed normalized trace with activation `1.0`, `decay_rate=0.1`, no reinforcement:

```text
tick=1 before=1.000 after=0.900 updated_at 0->0 last_decay 0->1
tick=2 before=0.900 after=0.800 updated_at 0->0 last_decay 1->2
tick=3 before=0.800 after=0.700 updated_at 0->0 last_decay 2->3
tick=4 before=0.700 after=0.600 updated_at 0->0 last_decay 3->4
tick=5 before=0.600 after=0.500 updated_at 0->0 last_decay 4->5
```

Decay no longer compounds by repeatedly using the old `updated_at_tick`.
