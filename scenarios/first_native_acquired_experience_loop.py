"""RND-023: explicit isolated experiment owner; never an ordinary Heart hook."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from clc.action.decision_selector import DecisionSelector
from clc.actuation.remembered_action_execution import NFPRememberedActionExecutionCoordinator
from clc.actuation.synthetic_exploration import SyntheticExplorationConfig, SyntheticExplorationAuthorization
from clc.context.context_memory import ContextMemory
from clc.context.context_memory_manager import ContextMemoryManager
from clc.context.context_ops_pool import ContextOpsPool
from clc.context.short_memory import ShortMemory
from clc.core.ids import IdGenerator
from clc.core.pattern_registry import PatternRegistry
from clc.experience.bounded_native_acquisition import BoundedNativeAcquisition
from clc.experience.expsm_native_create import NFPExpSMCreateWriter
from clc.expsm.expsm_activation_module import ExpSMActivationModule
from clc.expsm.nfp_operational_retrieval import NFPExpSMRetriever, NFPExpSMRetrievalConfig
from clc.runtime.memory_mutation_policy import policy_for_profile
from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits, Control
from clc.runtime.native_heart_session import NativeHeartComponents
from clc.system.mode_action_guard import ModeActionGuard
from clc.system.system_state import SystemState
from scenarios.support.synthetic_closed_loop_visual_world import SyntheticClosedLoopVisualWorld

EMPTY = {'experience': {}, 'reflexes': {}}


def make_session(root: Path, *, store=None, training=False, mode='active',
                 sample_enabled=None, profile='mutating_memory', hook=None, training_actions=3):
    """Fresh identical world/components; all writable paths confined to /tmp."""
    if type(training_actions) is not int or not 1 <= training_actions <= 7:
        raise ValueError('training requires 1..7 bounded actions')
    root = Path(root).resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    if root == temporary or not root.is_relative_to(temporary):
        raise ValueError('dedicated temporary experiment root required')
    root.mkdir(parents=True, exist_ok=False)
    path = root / 'ExpSM.json'
    path.write_text(json.dumps(EMPTY if store is None else store))
    ids = IdGenerator()
    registry = PatternRegistry(root / 'manifest.json')
    world = SyntheticClosedLoopVisualWorld(shape=(1, 2), initial_row=0, initial_column=0)
    components = NativeHeartComponents(
        world, ContextMemoryManager(ContextMemory(ids, registry), ContextOpsPool()),
        NFPExpSMRetriever(path), NFPExpSMRetrievalConfig(1.),
        ExpSMActivationModule(ids, registry, path), DecisionSelector(ids),
        NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(registry)),
        ShortMemory(8, 10), SystemState(mode=mode),
    )
    def ingress(tick, delivery):
        # Last pulse observes T+1, then pauses before any further selection.
        if tick == (training_actions if training else 1):
            delivery.accept(Control.PAUSE, source_id='rnd023-owner', stream_id='control')
    options = {}
    if training:
        options = dict(
            exploration_config=SyntheticExplorationConfig('rnd023-round-robin', ((0., 1.), (1., 0.)), training_actions, training_actions),
            exploration_authorization=SyntheticExplorationAuthorization('rnd023-owner', 'rnd023-permit', 'rnd023-round-robin'),
        )
    session = NativeDeliverySession(components, max_ticks=training_actions + 1 if training else 2,
        ingress=ingress, limits=DeliveryLimits(journal_capacity=128),
        sample_enabled=sample_enabled, **options)
    writer = NFPExpSMCreateWriter(path, policy_for_profile(profile, memory_root=root,
        memory_is_temporary=True), failure_hook=hook)
    return session, writer, path


def training(root, **options):
    session, writer, path = make_session(root, training=True, **options)
    owner = BoundedNativeAcquisition(session, isolated_root=root, writer=writer)
    session.run()
    return session, owner, writer, path


def admit_all(session, owner):
    # Admit the entire retained set, including the intervening left action.
    # Do not choose evidence using a predeclared target effect.
    return tuple(owner.admit(t) for t in session.components.short_memory.snapshot())


def prepare(owner):
    owner.seal()
    supported = [c for c in owner.candidates if c.support_count >= 2]
    if len(supported) != 1:
        return None
    return owner.prepare(supported[0].candidate_id)
