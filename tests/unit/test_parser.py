from patternity.simfile.parser import StepmaniaFileParser


def test_multiline_header_values_are_parsed() -> None:
    data = (
        "#TITLE:t;\n"
        "#BPMS:0.000=128.000\n,4.000=64.000\n;\n"
        "#NOTES:\n     dance-single:\n     t:\n     Challenge:\n     1:\n"
        "     0,0,0,0,0:\n1000\n0000\n0000\n0000\n,\n1000\n0000\n0000\n0000\n;\n"
    )
    song = StepmaniaFileParser.parse(data)
    assert song.header.bpms == {0.0: 128.0, 4.0: 64.0}
    second = song.charts[0].notes[1]
    assert second.timestamp is not None
    assert abs(second.timestamp - 4 * 60 / 128) < 1e-9
