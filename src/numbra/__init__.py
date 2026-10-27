from ._version import __version__ as __version__

__all__ = ["__version__", "app", "main"]


def __getattr__(name: str) -> object:
    if name == "app":
        from .cli import app

        return app
    raise AttributeError(name)


def main() -> None:
    from .cli import app

    app()
