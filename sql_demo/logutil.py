"""Small stdout logger for the setup steps."""


def log(component: str, message: str) -> None:
    print(f"[{component}] {message}", flush=True)
