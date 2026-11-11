from pathlib import Path

import pytest

from patternity import cli

MINIMAL_SIMFILE = """\
#TITLE:foo;
#ARTIST:bar;
#BPMS:0.000=120.000;
#NOTES:
     dance-single:
     :
     Beginner:
     1:
     0.000,0.000,0.000,0.000,0.000,0,0,0,0,0,0:
0000
,
;
"""


@pytest.fixture
def simfile() -> Path:
    return Path("/tmp/chart.ssc")


@pytest.fixture
def mock_read(mocker):
    return mocker.patch("patternity.cli.read_simfile", return_value=MINIMAL_SIMFILE)


def test_parse_only_valid(mocker, simfile) -> None:
    read_simfile = mocker.patch(
        "patternity.cli.read_simfile",
        return_value=MINIMAL_SIMFILE,
    )
    analyzer = mocker.patch("patternity.cli.analyze_chart")
    serialize = mocker.patch("patternity.cli.serialize")

    exit_code = cli.main(["-f", str(simfile)])

    assert exit_code == 0
    read_simfile.assert_called_once_with(simfile)
    analyzer.assert_not_called()
    serialize.assert_not_called()


def test_analyze_valid(mocker, simfile) -> None:
    mocker.patch(
        "patternity.cli.read_simfile",
        return_value=MINIMAL_SIMFILE,
    )

    analyzer = mocker.patch("patternity.cli.analyze_chart")
    analyzer.return_value.to_dict.return_value = {
        "basic": {},
        "tech": {},
        "movement": {},
    }

    exit_code = cli.main(["-f", str(simfile), "-a"])

    assert exit_code == 0
    analyzer.assert_called_once()
    analyzer.return_value.to_dict.assert_called_once()


def test_serialize_valid(mocker, simfile) -> None:
    mocker.patch(
        "patternity.cli.read_simfile",
        return_value=MINIMAL_SIMFILE,
    )

    output_path = mocker.patch("patternity.cli.output_path")
    output_path.return_value = Path("data/chart.json")

    serialize = mocker.patch("patternity.cli.serialize")
    serialize.return_value = Path("data/chart.json")

    exit_code = cli.main(["-f", str(simfile), "-s"])

    assert exit_code == 0
    output_path.assert_called_once_with(Path("/tmp/chart.ssc"), Path("data"))
    serialize.assert_called_once()


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_analyze_labels_each_chart_end_to_end(capsys) -> None:
    exit_code = cli.main(["-f", str(FIXTURES / "patterns" / "jacks.sm"), "-a"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Challenge" in out
    assert "'jacks':" in out


def test_serialize_creates_the_output_directory(tmp_path: Path) -> None:
    out_dir = tmp_path / "not" / "there"
    source = FIXTURES / "patterns" / "jacks.sm"

    assert cli.main(["-f", str(source), "-s", "-o", str(out_dir)]) == 0
    assert (out_dir / "jacks.json").is_file()


def test_output_without_serialize_is_a_usage_error(simfile, mock_read) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["-f", str(simfile), "-o", "somewhere"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize("name", ["chart.txt", "missing.sm"])
def test_unreadable_file_reports_an_error(tmp_path: Path, capsys, name: str) -> None:
    assert cli.main(["-f", str(tmp_path / name)]) == 1
    assert "Error:" in capsys.readouterr().out


def test_skipped_charts_are_reported(mocker, simfile, capsys) -> None:
    doubles = MINIMAL_SIMFILE.replace("dance-single", "dance-double")
    mocker.patch("patternity.cli.read_simfile", return_value=doubles)

    assert cli.main(["-f", str(simfile), "-a"]) == 0
    assert "Skipped dance-double Beginner chart" in capsys.readouterr().out
