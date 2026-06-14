from clc.core.activation_ids import aud_activation_id, img_activation_id, sen_activation_id
from clc.core.ids import IdGenerator
from clc.core.markers import OperationMarker
from clc.core.nfp import NFPFrame
from clc.core.operations import ContextOperation
from clc.core.pattern_registry import PatternRegistry


class InputPreprocessor:
    def __init__(self, id_gen: IdGenerator, pattern_registry: PatternRegistry) -> None:
        self.id_gen = id_gen
        self.pattern_registry = pattern_registry

    def audio(self, tick: int, frequencies: dict[int, float]) -> ContextOperation:
        max_value = max([abs(value) for value in frequencies.values()] + [1.0])
        activations = {self.pattern_registry.id(aud_activation_id(freq)): abs(value) / max_value for freq, value in frequencies.items()}
        return self._frame_operation(tick, "aud", activations)

    def image(self, tick: int, pixels: list[list[tuple[float, float, float]]]) -> ContextOperation:
        activations: dict[str, float] = {}
        for y, row in enumerate(pixels):
            for x, (red, green, blue) in enumerate(row):
                activations[self.pattern_registry.id(img_activation_id(x, y, "r"))] = _norm_rgb(red)
                activations[self.pattern_registry.id(img_activation_id(x, y, "g"))] = _norm_rgb(green)
                activations[self.pattern_registry.id(img_activation_id(x, y, "b"))] = _norm_rgb(blue)
        return self._frame_operation(tick, "img", activations)

    def sensor(self, tick: int, cpu_temp: float, memory_usage: float, damage_flag: bool, resource_pressure: float) -> ContextOperation:
        activations = {
            self.pattern_registry.id(sen_activation_id("cpu_temp_high")): _ramp(cpu_temp, low=60.0, high=95.0),
            self.pattern_registry.id(sen_activation_id("memory_pressure")): _ramp(memory_usage, low=0.65, high=1.0),
            self.pattern_registry.id(sen_activation_id("integrity_warning")): 1.0 if damage_flag else 0.0,
            self.pattern_registry.id(sen_activation_id("resource_pressure")): _ramp(resource_pressure, low=0.4, high=1.0),
        }
        return self._frame_operation(tick, "sen", activations)

    def _frame_operation(self, tick: int, source: str, activations: dict[str, float]) -> ContextOperation:
        frame = NFPFrame(
            frame_id=self.id_gen.next("frame"),
            tick=tick,
            origin="external",
            source=source,
            activations=activations,
        )
        return ContextOperation(
            op_id=self.id_gen.next("op"),
            marker=OperationMarker.RAW_INPUT_WRITE,
            tick=tick,
            source_module="input_preprocessor",
            target=None,
            payload={"frame": frame},
        )


def _norm_rgb(value: float) -> float:
    if value > 1.0:
        return max(0.0, min(1.0, value / 255.0))
    return max(0.0, min(1.0, value))


def _ramp(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)
