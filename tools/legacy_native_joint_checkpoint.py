"""RND-015 test-only, finite lifecycle driver. No production scheduler or routing.

Adapters own separate TemporaryDirectories. Legacy accepts only real feed inputs;
its pause/stop are driver admission gates, not new CLCRuntime lifecycle methods.
Native lifecycle and tick authority are delegated to the existing B2 owner.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from clc.runtime.runtime_phase_map import RUNTIME_PHASE_MAP
from clc.scenarios.scenario_runner import _runtime_for_fixture, _regression_summary
from clc.runtime.native_bounded_delivery import NativeDeliverySession, DeliveryLimits
# Reuse the prepared B2 fixture and passive production subclasses, not its tests.
from verify_native_heart_b2 import (
    World, Manager, Retriever, Short, NativeHeartComponents, PatternRegistry,
    IdGenerator, ContextMemory, ContextOpsPool, NFPExpSMRecordV1,
    SerializedNFPContextV1, SerializedNFPActionV1, SerializedObservedEffectV1,
    ExpSMOperationalMetadataV1, NFPExpSMCreationMetadataV1,
    NFPExpSMRetrievalConfig, ExpSMActivationModule, DecisionSelector,
    NFPRememberedActionExecutionCoordinator, ModeActionGuard, SystemState,
)


def inventory(root=ROOT / 'Memory'):
    """Complete file-name, size and SHA-256 inventory, including ignored files."""
    return {str(p.relative_to(root)): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob('*') if p.is_file()}


def plain(value):
    """Lossless trace projection: no float rounding, ID or timestamp suppression."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


class LegacyAdapter:
    def __init__(self, fixture):
        if fixture.synthetic_decision_cycle_summaries:
            raise ValueError('joint feed fixtures must not inject synthetic summaries')
        if any(i.kind not in ('audio', 'sensor', 'image') for i in fixture.inputs):
            raise ValueError('joint legacy adapter accepts public feed inputs only')
        self.temp = tempfile.TemporaryDirectory(prefix='rnd015-legacy-')
        self.root = Path(self.temp.name) / 'Memory'
        try:
            shutil.copytree(ROOT / 'Memory', self.root)
            self.runtime = _runtime_for_fixture(fixture, self.root)
        except BaseException:
            self.temp.cleanup()
            raise
        self.fixture = fixture
        self.state = 'ready'
        self.feeds = []
        self.phases = []
        self.drains = []
        self._phase = None
        self._tick = None
        # Passive wrappers call the original exactly once and preserve its return.
        for entry in RUNTIME_PHASE_MAP:
            name = entry.location_hint.split('.')[-1]
            original = getattr(self.runtime, name)
            def observed(*args, _call=original, _id=entry.phase_id, **kwargs):
                self._phase = _id
                record = {'tick': self._tick, 'phase': _id, 'before': self.snapshot()}
                self.phases.append(record)
                result = _call(*args, **kwargs)
                record['after'] = self.snapshot()
                return result
            setattr(self.runtime, name, observed)
        drain = self.runtime.ops_pool.drain
        def observed_drain():
            result = drain()
            self.drains.append((self._tick, self._phase, plain(result)))
            return result
        self.runtime.ops_pool.drain = observed_drain

    def snapshot(self):
        r = self.runtime
        return {'events': plain(r.memory.events),
                'candidates': plain(r.action_candidate_field.get_top_candidates(limit=10000))}

    def start(self):
        if self.state == 'ready':
            self.state = 'running'

    def pause(self):
        if self.state == 'running':
            self.state = 'paused'

    def resume(self):
        if self.state == 'paused':
            self.state = 'running'

    def stop(self):
        self.state = 'stopped'

    def feed(self, item):
        if self.state != 'running':
            return False  # rejected input is never queued for later execution
        self._tick = item.tick
        p = item.payload
        with redirect_stdout(io.StringIO()):
            if item.kind == 'audio':
                self.runtime.feed_audio(item.tick, {int(k): float(v) for k, v in p.get('frequencies', {}).items()})
            elif item.kind == 'sensor':
                self.runtime.feed_sensor(item.tick, float(p.get('cpu_temp', 40)),
                    float(p.get('memory_usage', .2)), bool(p.get('damage_flag', False)),
                    float(p.get('resource_pressure', 0)))
            elif item.kind == 'image':
                self.runtime.feed_image(item.tick, p.get('pixels', []))
            else:
                raise ValueError('unsupported legacy feed')
        self.feeds.append((item.kind, item.tick))
        return True

    def summary(self):
        from collections import Counter
        markers = [e.marker.value for e in self.runtime.memory.events]
        return _regression_summary(self.fixture, self.runtime, markers, dict(Counter(markers)))

    def close(self):
        self.stop()
        self.phases.clear()
        self.drains.clear()
        self.temp.cleanup()


class NativeAdapter:
    def __init__(self, *, ticks=5, empty=False, sensing=True, flood=False, failure=None, mode='active'):
        self.temp = tempfile.TemporaryDirectory(prefix='rnd015-native-')
        self.root = Path(self.temp.name)
        self.events = []
        try:
            path = self.root / 'ExpSM.json'
            records = {}
            for col in range(3):
                values = tuple(float(i == col) for i in range(4))
                record = NFPExpSMRecordV1(
                    str(col), SerializedNFPContextV1('visual', (1, 4), (values,)),
                    SerializedNFPActionV1('action', (2,), (0., 1.)),
                    SerializedObservedEffectV1('visual', (1, 4),
                        tuple(float(i == col + 1) - values[i] for i in range(4))),
                    ExpSMOperationalMetadataV1(5, 0, .8, .9),
                    NFPExpSMCreationMetadataV1(2, f'fixture:{col}', 0))
                records[str(col)] = record.to_json_data()
            path.write_text(json.dumps({'experience': {} if empty else records, 'reflexes': {}}))
            self.store_bytes = path.read_bytes()
            self.store_path = path
            self.registry = PatternRegistry(self.root / 'manifest.json')
            ids = IdGenerator()
            manager = Manager(ContextMemory(ids, self.registry), ContextOpsPool())
            manager.events, manager.pending_log = self.events, []
            retriever = Retriever(path)
            retriever.calls = []
            short = Short(8, 10)
            short.events, short.fail = self.events, False
            world = World(self.events, failure)
            components = NativeHeartComponents(world, manager, retriever, NFPExpSMRetrievalConfig(.99),
                ExpSMActivationModule(ids, self.registry, path), DecisionSelector(ids, decision_threshold=.35),
                NFPRememberedActionExecutionCoordinator(ids, ModeActionGuard(self.registry)),
                short, SystemState(mode=mode))
            def ingress(tick, delivery):
                if flood:
                    from clc.transduction import VisualFieldSnapshot
                    for i in range(100):
                        delivery.accept(VisualFieldSnapshot((1, 4), (1., 0., 0., 0.), tick, i),
                                        source_id='noise', stream_id='optional')
            self.session = NativeDeliverySession(components, max_ticks=ticks,
                limits=DeliveryLimits(sensory_capacity=2, dispatch_budget=2, journal_capacity=400),
                ingress=ingress, sample_enabled=lambda tick: sensing)
        except BaseException:
            self.temp.cleanup()
            raise

    def start(self):
        return self.session.start()

    def pause(self):
        return self.session.pause()

    def resume(self):
        return self.session.resume()

    def stop(self):
        return self.session.stop()

    def step(self):
        return self.session.step()  # no tick argument: Heart is the sole authority

    def close(self):
        if getattr(self, '_closed', False):
            return
        self._closed = True
        try:
            self.stop()
            if self.store_path.read_bytes() != self.store_bytes:
                raise AssertionError('native prepared ExpSM changed')
        finally:
            self.temp.cleanup()


class JointLifecycle:
    """Finite caller plan, separate results, no implicit ticks or cross delivery.

    Failure closes only that adapter's admission. The other may complete explicitly
    planned work. Native stop reports retain pending/uncertain physical execution.
    No result, exception or stop is interpreted as a request to retry.
    """
    def __init__(self, legacy, native, *, max_operations=128):
        if type(max_operations) is not int or not 1 <= max_operations <= 128:
            raise ValueError('test plan budget must be 1..128')
        self.adapters = {'legacy': legacy, 'native': native}
        self.max_operations = max_operations
        self.results = {'legacy': [], 'native': []}
        self.errors = {}
        self.used = 0

    def run(self, plan):
        plan = tuple(plan)
        if self.used + len(plan) > self.max_operations:
            raise ValueError('test plan budget exceeded before dispatch')
        for target, method, argument in plan:
            if target not in self.adapters or method not in ('start', 'pause', 'resume', 'stop', 'feed', 'step'):
                raise ValueError('unsupported test command')
            if (method == 'feed' and target != 'legacy') or (method == 'step' and target != 'native'):
                raise ValueError('adapter boundary mismatch')
        for target, method, argument in plan:
            self.used += 1
            if target in self.errors:
                continue
            adapter = self.adapters[target]
            try:
                result = getattr(adapter, method)(argument) if method == 'feed' else getattr(adapter, method)()
                self.results[target].append((method, result))
            except Exception as exc:
                self.errors[target] = {'type': type(exc).__name__, 'message': str(exc)}
                adapter.stop()
        return {'results': self.results, 'errors': self.errors,
                'native_stop': self.adapters['native'].session.stop_report()}
