def img_activation_id(x: int, y: int, channel: str) -> str:
    return f"img_x{x}_y{y}_{channel.lower()}"


def aud_activation_id(freq: str | float | int) -> str:
    return f"aud_freq_{_freq_text(freq)}"


def sen_activation_id(name: str) -> str:
    return f"sen_{name}"


def tone_activation_id(name: str) -> str:
    return f"tone_{name}"


def _freq_text(freq: str | float | int) -> str:
    if isinstance(freq, float) and freq.is_integer():
        return str(int(freq))
    return str(freq)
