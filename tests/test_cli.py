from click.testing import CliRunner
from scripts.cli import cli


def test_cli_fields_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["fields"])
    assert result.exit_code == 0
    assert "VALID POST FIELDS" in result.output
    assert "VALID COMMENT FIELDS" in result.output
    assert "created_utc" in result.output
    assert "parent_id" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Reddit Research Scraper" in result.output
    assert "run" in result.output
    assert "posts" in result.output
    assert "comments" in result.output


def test_cli_field_validation_error():
    runner = CliRunner()
    # Passing an invalid field name to --include-fields
    result = runner.invoke(cli, ["run", "--from", "2024-01-01", "-i", "totally_bogus_field_xyz"])
    assert result.exit_code == 1
    assert "Field Validation Error" in result.output


def test_cli_required_field_exclusion_error():
    runner = CliRunner()
    # Excluding required field 'id'
    result = runner.invoke(cli, ["run", "--from", "2024-01-01", "-e", "id"])
    assert result.exit_code == 1
    assert "Required field 'id' cannot be excluded" in result.output
