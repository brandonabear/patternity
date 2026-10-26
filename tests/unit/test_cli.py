from pathlib import Path

import pytest

from patternity import cli

MINIMAL_SIMFILE = """\
#TITLE:foo;
#ARTIST:bar;
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
    analyzer = mocker.patch("patternity.cli.Analyzer")
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

    analyzer = mocker.patch("patternity.cli.Analyzer")
    analyzer.return_value.analyze.return_value = {
        "basic": {},
        "tech": {},
        "movement": {},
    }

    exit_code = cli.main(["-f", str(simfile), "-a"])

    assert exit_code == 0
    analyzer.assert_called_once()
    analyzer.return_value.analyze.assert_called_once()


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
