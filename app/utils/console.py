from datetime import datetime


def log_step(step: str, message: str) -> None:
    print(f"[{_now()}] {step} {message}")


def log_info(message: str) -> None:
    print(f"[{_now()}] {message}")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")
