"""Explicit synthetic bootstrap, not a learned strategy or acquisition authority."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from uuid import UUID, uuid4
import weakref

from clc.patterns import NFPFrame, NFPWindow, PatternModality, PatternOrigin


def _identity(value):
    if not isinstance(value, str) or not 0 < len(value) <= 256:
        raise ValueError('identity must contain 1..256 characters')


@dataclass(frozen=True)
class SyntheticExplorationConfig:
    configuration_id: str
    commands: tuple[tuple[float, float], ...]
    max_intents: int = 1
    max_actions: int = 1
    intent_lifetime_ticks: int = 0

    def __post_init__(self):
        _identity(self.configuration_id)
        if not isinstance(self.commands, tuple) or not 1 <= len(self.commands) <= 16:
            raise ValueError('provide 1..16 immutable motor commands')
        for command in self.commands:
            if (not isinstance(command, tuple) or len(command) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or not 0 <= v <= 1 for v in command)):
                raise ValueError('motor commands require two finite values in [0,1]')
        for value in (self.max_intents, self.max_actions):
            if type(value) is not int or not 0 <= value <= 64:
                raise ValueError('budgets must be integers in [0,64]')
        if self.max_actions > self.max_intents:
            raise ValueError('action budget cannot exceed intent budget')
        # Immediate native context only; no queued intent survives a pulse.
        if type(self.intent_lifetime_ticks) is not int or self.intent_lifetime_ticks != 0:
            raise ValueError('first pass supports same-tick intents only')


@dataclass(frozen=True)
class SyntheticExplorationAuthorization:
    test_owner_id: str
    authorization_id: str
    configuration_id: str

    def __post_init__(self):
        for value in (self.test_owner_id, self.authorization_id, self.configuration_id):
            _identity(value)


@dataclass(frozen=True)
class ExploratoryIntent:
    intent_id: str
    authorization_id: str
    test_owner_id: str
    configuration_id: str
    session_id: str
    context_window_id: str
    context_tick: int
    expires_tick: int
    command: tuple[float, float]

    def __post_init__(self):
        for name in ('intent_id', 'authorization_id', 'test_owner_id', 'configuration_id',
                     'session_id', 'context_window_id'):
            _identity(getattr(self, name))
        if (type(self.context_tick) is not int or not 0 <= self.context_tick < 2**63
                or self.expires_tick != self.context_tick):
            raise ValueError('exploratory intent must bind one current tick')
        # Reuse bounded motor validation, without introducing an effect or reward.
        SyntheticExplorationConfig(self.configuration_id, (self.command,))


@dataclass(frozen=True)
class MaterializedExploratoryAction:
    exploratory_intent: ExploratoryIntent
    action_frame: NFPFrame
    before_context_at_T: NFPWindow
    execution_occurrence_id: str

    def __post_init__(self):
        if not isinstance(self.exploratory_intent, ExploratoryIntent):
            raise TypeError('typed exploratory intent required')
        frame, context, intent = self.action_frame, self.before_context_at_T, self.exploratory_intent
        if not isinstance(frame, NFPFrame) or not isinstance(context, NFPWindow):
            raise TypeError('materialized exploration requires native frame and context')
        if (frame.modality is not PatternModality.ACTION
                or frame.origin is not PatternOrigin.ACTION_GENERATED
                or frame.active_tick != intent.context_tick
                or context.end_tick != intent.context_tick
                or context.window_id != intent.context_window_id
                or frame.values != intent.command):
            raise ValueError('exploratory action/context binding mismatch')
        for value in (frame.frame_id, self.execution_occurrence_id):
            parsed = UUID(value)
            if parsed.version != 4 or str(parsed) != value:
                raise ValueError('fresh canonical UUIDv4 required')
        if len({frame.frame_id, self.execution_occurrence_id, intent.intent_id}) != 3:
            raise ValueError('execution identities must be independent')


@dataclass(frozen=True)
class ExplorationDiagnostic:
    intent: ExploratoryIntent
    admitted: bool = False
    guarded: bool = False
    applied: bool = False
    denied: bool = False
    uncertain: bool = False
    outcome: str = 'issued'
    execution_occurrence_id: str | None = None


@dataclass(slots=True)
class ExploratoryExecutionReceipt:
    """One coordinator-owned factual handoff, never a result or apply authority.

    Only coordinator writes execution fields, immediately at the corresponding
    boundary. Plain bounded scalars; no callbacks, runtime objects or exceptions.
    """
    intent_id: str
    execution_occurrence_id: str | None = None
    guard_passed: bool = False
    apply_entry: bool = False
    apply_returned: bool = False
    pending_registered: bool = False
    result_status: str | None = None


class SyntheticExplorationPolicy:
    """Session-owned finite round robin; never sees hidden state or effects.

    Reservation precedes coordinator work. Entries are never evicted/retried;
    at most 64 scalar diagnostics, no session/world/callback references retained.
    """

    def __init__(self, config, authorization, session_id, world=None):
        if not isinstance(config, SyntheticExplorationConfig):
            raise TypeError('explicit exploration config required')
        if authorization is not None and not isinstance(authorization, SyntheticExplorationAuthorization):
            raise TypeError('typed test-owner authorization required')
        _identity(session_id)
        if authorization is not None and authorization.configuration_id != config.configuration_id:
            raise ValueError('authorization configuration mismatch')
        from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld
        if not isinstance(world, SyntheticClosedLoopVisualWorld):
            raise ValueError('exploration requires an owned synthetic world')
        self._world_ref = weakref.ref(world)
        self._context_ref = None
        self.config = config
        self.authorization = authorization
        self.session_id = session_id
        self._entries: list[ExplorationDiagnostic] = []
        self._awaiting: str | None = None
        self._blocked = False
        self._execution_receipt: ExploratoryExecutionReceipt | None = None
        self._recovery_attempted_for: str | None = None
        self.diagnostic_recovery_failed = False
        self.diagnostic_projection_failed = False

    @property
    def diagnostics(self):
        return tuple(self._entries)

    def issue(self, context, *, tick, pending, unresolved):
        if (self.authorization is None or self._blocked or self._awaiting is not None
                or pending is not None or unresolved
                or len(self._entries) >= self.config.max_intents
                or sum(e.admitted for e in self._entries) >= self.config.max_actions):
            return None
        if (not isinstance(context, NFPWindow) or context.end_tick != tick
                or type(tick) is not int or not 0 <= tick < 2**63
                or len(context.frames) > 8
                or any(len(f.values) > 4096 for f in context.frames)):
            return None
        _identity(context.window_id)
        if self._entries and self._entries[-1].intent.context_tick >= tick:
            return None
        self._context_ref = weakref.ref(context)
        auth = self.authorization
        intent = ExploratoryIntent(str(uuid4()), auth.authorization_id, auth.test_owner_id,
            self.config.configuration_id, self.session_id, context.window_id, tick, tick,
            self.config.commands[len(self._entries) % len(self.config.commands)])
        self._entries.append(ExplorationDiagnostic(intent))
        return intent

    def admit(self, intent, context, world):
        from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld
        # Exact issued object: copied or fabricated intent cannot exercise authority.
        index = next((i for i, e in enumerate(self._entries) if e.intent is intent), None)
        if index is None or self._entries[index].outcome != 'issued':
            return False
        entry = self._entries[index]
        valid = (not self._blocked and self._awaiting is None and self.authorization is not None
                 and isinstance(world, SyntheticClosedLoopVisualWorld) and world is self._world_ref()
                 and self._context_ref is not None and context is self._context_ref()
                 and context is not None and context.window_id == intent.context_window_id
                 and context.end_tick == intent.context_tick == world.current_tick
                 and sum(e.admitted for e in self._entries) < self.config.max_actions)
        self._entries[index] = replace(entry, admitted=valid, denied=not valid,
                                        outcome='admitted' if valid else 'denied')
        return valid

    @property
    def execution_receipt(self):
        return self._execution_receipt

    def _new_execution_receipt(self, intent):
        receipt = ExploratoryExecutionReceipt(intent.intent_id)
        self._execution_receipt = receipt
        return receipt

    def bind_execution(self, intent, occurrence):
        """Diagnostic identity only; this does not prove guard or world apply."""
        index = next(i for i, e in enumerate(self._entries) if e.intent is intent)
        self._entries[index] = replace(self._entries[index], execution_occurrence_id=occurrence)

    def pass_guard(self, intent):
        index = next(i for i, e in enumerate(self._entries) if e.intent is intent)
        self._entries[index] = replace(self._entries[index], guarded=True, outcome='guarded')

    def enter_apply(self, intent):
        """Checkpoint immediately before the potentially mutating call."""
        index = next(i for i, e in enumerate(self._entries) if e.intent is intent)
        self._entries[index] = replace(self._entries[index], guarded=True, outcome='applying')

    def confirm_pending(self, intent):
        """Apply returned and the authoritative coordinator registered pending."""
        from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as S
        index = next(i for i, e in enumerate(self._entries) if e.intent is intent)
        entry = self._entries[index]
        self._entries[index] = replace(entry, applied=True, outcome=S.ACTION_EXECUTED_OBSERVATION_PENDING.value)
        self._awaiting = entry.execution_occurrence_id

    def finish(self, intent, result):
        self._record_result(intent, result)

    def _record_result(self, intent, result):
        from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionStatus as S
        index = next(i for i, e in enumerate(self._entries) if e.intent is intent)
        e = self._entries[index]
        guarded = result.guard_passed
        applied = result.status is S.ACTION_EXECUTED_OBSERVATION_PENDING and not result.detail
        uncertain = result.actuator_signal is not None and not applied
        self._entries[index] = replace(e, guarded=guarded, applied=applied,
            denied=result.actuator_signal is None, uncertain=uncertain, outcome=result.status.value,
            execution_occurrence_id=result.execution_occurrence_id)
        if applied:
            self._awaiting = result.execution_occurrence_id
        if uncertain:
            self._blocked = True

    def observe(self, recent):
        if recent is not None and recent.execution_occurrence_id == self._awaiting:
            self._awaiting = None

    def interrupt(self, intent, result=None):
        """Publish coordinator facts; optimistic diagnostic markers are not proof."""
        return self._recover_receipt(intent)

    def _recover_receipt(self, intent):
        receipt = self._execution_receipt
        index = next((i for i, e in enumerate(self._entries) if e.intent is intent), None)
        if index is None:
            return None
        self._blocked = True
        if receipt is None or receipt.intent_id != intent.intent_id:
            return None
        uncertain = receipt.apply_entry and not receipt.pending_registered
        outcome = receipt.result_status or (
            'pending_registered' if receipt.pending_registered else
            'execution_interrupted_no_retry' if receipt.apply_entry else
            'interrupted_before_apply'
        )
        self._entries[index] = replace(
            self._entries[index], guarded=receipt.guard_passed,
            applied=receipt.pending_registered, uncertain=uncertain,
            denied=not receipt.apply_entry, outcome=outcome,
            execution_occurrence_id=receipt.execution_occurrence_id,
        )
        if receipt.apply_entry:
            self._awaiting = receipt.execution_occurrence_id
            return receipt.execution_occurrence_id
        return None

    def recover_interruption(self, intent):
        """Secondary-error containment, called only with a primary exception active.

        A failing recovery marker is never retried. The private scalar projection
        is separate from that marker. If projection itself fails, retain the
        receipt and explicit failure flags, never replace the primary exception.
        """
        if intent is None:
            return None
        if self._recovery_attempted_for == intent.intent_id:
            return None
        self._recovery_attempted_for = intent.intent_id
        self._blocked = True
        try:
            return self.interrupt(intent)
        except BaseException:
            self.diagnostic_recovery_failed = True
            self._blocked = True
            try:
                return self._recover_receipt(intent)
            except BaseException:
                self.diagnostic_projection_failed = True
                return None
