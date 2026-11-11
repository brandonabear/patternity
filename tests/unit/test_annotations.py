import pytest

from patternity.footing.stance import FootMove
from patternity.training.annotations import (
    PATTERN_TAGS,
    UNSCORED_PATTERN_TAGS,
    AnnotationError,
    parse_annotated_sm,
)
from tests.helpers import chart_text


@pytest.mark.parametrize(
    "comment",
    [
        "@foot=R7",
        "@foot=l",
        "@foot=L,R",
        "@feet=L,",
        "@feet=L,X",
        "@pattern=Jack",
        "@pattern=footswich",
        "@pattern=jack,footswich",
        "@pattern=none",
    ],
)
def test_malformed_or_unknown_tag_raises_with_line_number(comment: str) -> None:
    with pytest.raises(AnnotationError, match=r"line \d+"):
        parse_annotated_sm(chart_text([f"1000 // {comment}", ","]))


def test_scored_and_unscored_pattern_tags_are_accepted() -> None:
    tags = ",".join(sorted(PATTERN_TAGS.keys() | UNSCORED_PATTERN_TAGS))
    annotated = parse_annotated_sm(chart_text([f"1000 // @foot=L @pattern={tags}", ","]))
    assert annotated.rows[0].patterns == PATTERN_TAGS.keys() | UNSCORED_PATTERN_TAGS


def test_suggestions_and_other_tags_are_ignored() -> None:
    rows = ["1000 // @suggest_foot=R @margin=1.0 @suggest_pattern=none note=x", ","]
    assert parse_annotated_sm(chart_text(rows)).tagged_assignments == {}


def test_first_of_a_repeated_tag_wins() -> None:
    annotated = parse_annotated_sm(chart_text(["1000 // @foot=L @foot=R", ","]))
    assert annotated.tagged_assignments == {0: FootMove.LEFT}
