import pytest

from patternity.simfile.reader import UnsupportedSimfileSuffix, read_simfile


@pytest.mark.parametrize(
    "suffix", [".sm", ".ssc"]
)
def test_read_simfile_success(mocker, suffix):
    file = mocker.Mock()
    file.name = f"chart{suffix}"
    file.suffix = suffix
    file.read_text.return_value = "#TITLE:foobar;"

    result = read_simfile(file)

    assert result == "#TITLE:foobar;"
    file.read_text.assert_called_once_with(encoding="utf-8")


@pytest.mark.parametrize(
    "suffix", [".txt", ".dwi"]
)
def test_read_simfile_failure(mocker, suffix):
    file = mocker.Mock()
    file.name = f"chart{suffix}"
    file.suffix = suffix

    with pytest.raises(UnsupportedSimfileSuffix):
        read_simfile(file)

    file.read_text.assert_not_called()
