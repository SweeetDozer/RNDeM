"""Explicit, single retained ECHO/DAR evaluation; no observation authority."""
from dataclasses import dataclass
from math import isclose
from uuid import uuid4

from clc.echo.expectations import EchoMatch
from clc.internal.admission import ComparisonRequest
from clc.internal.multitick import WindowSourceDescriptor
from clc.patterns import PatternOrigin


@dataclass(frozen=True)
class CandidateEvaluation:
    evaluation_id: str
    expectation_id: str
    source: WindowSourceDescriptor
    candidates: tuple[WindowSourceDescriptor, WindowSourceDescriptor]
    matches: tuple[EchoMatch, EchoMatch]
    requests: tuple[ComparisonRequest | None, ComparisonRequest | None]
    state: str
    # Signed structural advantage of candidates[0], never identity probability.
    score_delta: float | None = None
    preferred_observation_id: str | None = None
    origin: PatternOrigin = PatternOrigin.INTERNAL_STATE
    identity_confirmed: bool = False


class EchoCandidateComparison:
    """Caller-owned opt-in bridge using only public session/registry APIs.

    Exactly two requests per evaluation, one retained evaluation per bridge.
    Session serializes callers. No worker, tick hook, registry, retry or writes.
    Caller must not release owned DAR requests until release() (detected as
    insufficient data if it does). Metadata only is retained here, not NFP values.
    """

    def __init__(self, session):
        self._session = session
        self._binding = None
        # Cleanup authority exists independently of a fully published evaluation.
        self._owned_requests: list[str] = []

    def submit(self, expectation_id: str, candidate_ticks: tuple[int, int]) -> CandidateEvaluation:
        if self._binding is not None or self._owned_requests:
            raise ValueError('release previous evaluation first')
        ticks = tuple(candidate_ticks)
        if len(ticks) != 2 or any(type(t) is not int for t in ticks) or ticks[0] == ticks[1]:
            raise ValueError('two distinct observation ticks required')
        s = self._session
        if s.echo is None:
            raise ValueError('ECHO is not enabled')
        entry = next((e for e in s.echo.snapshot() if e.expectation_id == expectation_id), None)
        if entry is None or entry.state == 'contradicted' or s.heart.tick > entry.expires_at:
            raise ValueError('live non-contradicted expectation required')
        if not any(r.observation is entry.source for r in s.records) and not any(
                t.after_sensory_window is entry.source for t in s.components.short_memory.snapshot()):
            raise ValueError('source must be retained session evidence or ShortMemory evidence')
        # Read actual session observations and historical matches, never caller NFP.
        records = tuple(next((r for r in s.records if r.tick == t), None) for t in ticks)
        if any(r is None or r.observation is None for r in records):
            raise ValueError('retained session observations required')
        matches = tuple(next((m for m in r.echo_matches if
                              m.expectation_id == entry.expectation_id and
                              m.source_window_id == entry.source.window_id and
                              m.observation_id == r.observation.window_id), None) for r in records)
        if any(m is None or m.outcome in ('expired', 'contradiction', 'incomparable') for m in matches):
            raise ValueError('compatible non-contradictory ECHO observations required')
        # All fallible metadata preparation precedes the first admission.
        metadata = (str(uuid4()), entry.expectation_id,
                    WindowSourceDescriptor.capture(entry.source),
                    tuple(WindowSourceDescriptor.capture(r.observation) for r in records),
                    matches)
        try:
            for record in records:
                self._owned_requests.append(
                    s.submit_comparison_request(entry.source, record.observation).request_id)
            self._binding = (*metadata, tuple(self._owned_requests))
            return self.snapshot()
        except BaseException:
            # At this serialized boundary no pulse/dispatch can have occurred.
            # Roll back only our acceptance; never retry or disturb other work.
            self._binding = None
            self.release()
            raise

    def snapshot(self) -> CandidateEvaluation | None:
        if self._binding is None:
            return None
        eid, expectation, source, candidates, matches, ids = self._binding
        retained = {r.request_id: r for r in self._session.comparison_requests()}
        requests = tuple(retained.get(key) for key in ids)
        state, delta, preferred = 'pending', None, None
        if any(r is None or r.state in ('cancelled', 'failed') for r in requests):
            state = 'insufficient_data'
        elif all(r.state == 'completed' for r in requests):
            results = tuple(r.work.result if r.work else None for r in requests)
            if any(result is None for result in results):
                state = 'insufficient_data'
            else:
                delta = results[0].score - results[1].score
                if any(m.outcome != 'support' for m in matches):
                    state = 'insufficient_data'
                elif isclose(results[0].score, results[1].score, rel_tol=0., abs_tol=1e-12):
                    state = 'indistinguishable'
                else:
                    state = 'relative_similarity'
                    preferred = candidates[0 if delta > 0 else 1].window_id
        return CandidateEvaluation(eid, expectation, source, candidates, matches,
                                   requests, state, delta, preferred)

    def release(self) -> None:
        """One cleanup attempt; retain ownership on failure for explicit release.

        Read-only membership resolves external release and ambiguous exceptions.
        An exception (including KeyError) alone never proves that an ID is gone.
        """
        s = self._session
        try:
            for key in tuple(self._owned_requests):
                retained = {r.request_id for r in s.comparison_requests()}
                if key in retained:
                    try:
                        s.cancel_comparison_request(key)
                        s.release_comparison_request(key)
                    except BaseException:
                        # An API may have completed its effect before raising.
                        # If this read also fails, conservatively retain the ID.
                        if key not in {r.request_id for r in s.comparison_requests()}:
                            self._owned_requests.remove(key)
                        raise
                self._owned_requests.remove(key)
        finally:
            if not self._owned_requests:
                self._binding = None
