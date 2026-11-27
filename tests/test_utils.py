import re

import pytest

from mini_pycli.data import SpecialReturnValue
from mini_pycli.utils import Comparable, InputChecker, Range


class ComparableTest(Comparable):
    def __init__(self, char: str) -> None:
        self.char = char

    def in_range(self, lower_char: str, upper_char: str) -> bool:
        if len(lower_char) > 1 or len(upper_char) > 1:
            raise ValueError(f"{lower_char if len(lower_char) >
                                1 else upper_char} must be 1 character long")
        return ord(lower_char) <= ord(self.char) <= ord(upper_char)


@pytest.fixture
def _range() -> Range:
    return Range(1, 10)


@pytest.fixture
def custom_range() -> Range:
    return Range("a", "z")


@pytest.fixture
def input_checker() -> InputChecker:
    return InputChecker(
        lambda val: ComparableTest(val) if len(val) == 1 else SpecialReturnValue.INVALID_INPUT,
        ["a", "c", "f"],
        ["e"],
        Range("a", "z"),
    )


@pytest.fixture
def regex_input_checker() -> InputChecker:
    return InputChecker(
        regex=re.compile(
            r"^(?:(?:(?:0?[13578]|1[02])(\/|-|\.)31)\1|(?:(?:0?[13-9]|1[0-2])(\/|-|\.)(?:29|30)\2))(?:(?:1[6-9]|[2-9]\d)?\d{2})$|^(?:0?2(\/|-|\.)29\3(?:(?:(?:1[6-9]|[2-9]\d)?(?:0[48]|[2468][048]|[13579][26])|(?:(?:16|[2468][048]|[3579][26])00))))$|^(?:(?:0?[1-9])|(?:1[0-2]))(\/|-|\.)(?:0?[1-9]|1\d|2[0-8])\4(?:(?:1[6-9]|[2-9]\d)?\d{2})$"
        )
    )


def test_range(_range: Range, custom_range: Range) -> None:
    assert _range.check(1)
    assert _range.check(2)
    assert _range.check(10)
    assert _range.check(9.9)
    assert not _range.check(10.1)
    assert custom_range.check(ComparableTest("a"))
    assert custom_range.check(ComparableTest("z"))
    assert custom_range.check(ComparableTest("q"))
    assert not custom_range.check(ComparableTest("Z"))


def test_input_check(input_checker, regex_input_checker) -> None:
    assert input_checker.check("a")
    assert input_checker.check("c")
    assert input_checker.check("f")
    assert not input_checker.check("e")
    assert input_checker.check("foo") is SpecialReturnValue.INVALID_INPUT

    assert regex_input_checker.check("12/12/2000")
    assert not regex_input_checker.check("32/12/42")
