import subprocess
import sys


def test_core_import_does_not_load_terminal_dependencies() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from numbra.core import Challenge, Stats; "
            "assert not {'typer', 'rich', 'numbra.cli.app'} & sys.modules.keys()",
        ],
        check=True,
    )


def test_public_app_imports_refer_to_the_same_typer_app() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from numbra import app, main; from numbra.cli import app as cli_app; "
            "assert app is cli_app; assert callable(main)",
        ],
        check=True,
    )
