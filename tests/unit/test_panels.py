from patternity.simfile import PANELS, NoteRow, Panel
from tests.helpers import note_row


def test_panels_in_column_order() -> None:
    assert PANELS == (Panel.L, Panel.D, Panel.U, Panel.R)
    assert [Panel.at(col) for col in range(4)] == list(PANELS)
    assert [panel.column for panel in PANELS] == [0, 1, 2, 3]


def test_panel_set_operations() -> None:
    lu = Panel.L | Panel.U
    assert Panel.U in lu
    assert Panel.D not in lu
    assert Panel.L in lu and lu in Panel.L | Panel.U | Panel.R  # subset
    assert len(lu) == 2
    assert len(Panel.NONE) == 0
    assert list(lu) == [Panel.L, Panel.U]
    assert ~lu == Panel.D | Panel.R


def test_note_row_panel_sets() -> None:
    row = note_row("1M20")
    assert row.pressed == Panel.L | Panel.U
    assert row.mines == Panel.D


def test_note_row_active_panels_round_trip_json_keys() -> None:
    row = note_row("0000", holds_active=Panel.L, rolls_active=Panel.R)
    data = row.to_dict()
    assert data["hold_active_mask"] == 1
    assert data["roll_active_mask"] == 8
    assert "holds_active" not in data
    restored = NoteRow.from_dict(data)
    assert restored.holds_active == Panel.L
    assert restored.rolls_active == Panel.R
    assert "hold_active_mask" not in note_row("0000").to_dict()
