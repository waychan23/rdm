from typer.testing import CliRunner

from rdm import __version__
from rdm.interfaces.cli.main import app


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
