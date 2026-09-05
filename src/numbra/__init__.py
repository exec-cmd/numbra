from ._version import __version__ as __version__
from .cli import app


def main() -> None:
    app()
