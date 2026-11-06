"""DAR A0: bounded admission bookkeeping, no execution or world authority."""
from dataclasses import dataclass, replace
from uuid import uuid4

from clc.internal.multitick import WorkSnapshot, WorkLimits, validate_comparison
from clc.patterns import NFPWindow


@dataclass(frozen=True)
class AdmissionLimits:
    max_pending: int = 4
    max_requests: int = 8
    max_retained_cells: int = 16384

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')


@dataclass(frozen=True)
class ComparisonRequest:
    request_id: str
    order: int
    retained_cells: int
    state: str = 'queued'
    work: WorkSnapshot | None = None
    kind: str = 'structural_comparison'


class AdmissionRejected(ValueError):
    """Explicit rejection; no inputs or outcome slot were retained."""


class ComparisonAdmission:
    """Owner serializes calls. Each acceptance reserves its terminal slot.

    IDs are generated here, never supplied by callers. Released IDs disappear;
    no unbounded history or dedup registry. Coordinates are not a byte limit.
    """

    def __init__(self, limits: AdmissionLimits, work_limits: WorkLimits):
        self.limits = limits
        self.work_limits = work_limits
        self._requests = {}
        self._inputs = {}
        self._order = 0
        self.active = None

    def snapshots(self) -> tuple[ComparisonRequest, ...]:
        return tuple(self._requests.values())

    def submit(self, left: NFPWindow, right: NFPWindow, tick: int) -> ComparisonRequest:
        cells = validate_comparison(left, right, self.work_limits, tick)
        if len(self._requests) >= self.limits.max_requests:
            raise AdmissionRejected('request/outcome capacity exhausted; release terminal requests')
        if len(self._inputs) >= self.limits.max_pending:
            raise AdmissionRejected('pending queue exhausted')
        if sum(r.retained_cells for r in self._requests.values()) + cells > self.limits.max_retained_cells:
            raise AdmissionRejected('retained input coordinate budget exhausted')
        self._order += 1
        request = ComparisonRequest(str(uuid4()), self._order, cells)
        self._requests[request.request_id] = request
        self._inputs[request.request_id] = (left, right)
        return request

    def next_inputs(self):
        if self.active is None and self._inputs:
            key = next(iter(self._inputs))
            return key, self._inputs[key]
        return None

    def dispatched(self, key: str, work: WorkSnapshot):
        self._inputs.pop(key)
        self.active = key
        self.update(work)

    def update(self, work: WorkSnapshot):
        key = self.active
        request = self._requests[key]
        terminal = work.state in ('completed', 'cancelled', 'failed')
        self._requests[key] = replace(request, state=work.state, work=work,
                                      retained_cells=0 if terminal else request.retained_cells)
        if terminal:
            self.active = None

    def cancel_queued(self, key: str):
        request = self._requests[key]
        if key in self._inputs:
            self._inputs.pop(key)
            self._requests[key] = replace(request, state='cancelled', retained_cells=0)
        return self._requests[key]

    def release(self, key: str):
        if self._requests[key].state not in ('completed', 'cancelled', 'failed'):
            raise ValueError('cancel or complete request before release')
        del self._requests[key]
