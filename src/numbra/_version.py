from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("numbra")
except PackageNotFoundError:
    __version__ = "1.3.0"
