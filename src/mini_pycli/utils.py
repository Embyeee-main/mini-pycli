"""Optional input-validation helpers for mini-pycli.

These are building blocks for a node's ``input_parser``. They are not required:
an ``input_parser`` is just a function that returns a parsed value or
``SpecialReturnValue.INVALID_INPUT``.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from .data import SpecialReturnValue, U


class Comparable:
    """Base class for custom types that :class:`Range` can check.

    Subclass it and override :meth:`in_range` to let ``Range`` validate values
    that are not plain ``int`` or ``float``.
    """

    def in_range(self, _min: Any, _max: Any) -> bool:
        """Return whether this value lies between ``_min`` and ``_max``.

        Args:
            _min: Lower bound.
            _max: Upper bound.

        Returns:
            ``True`` if the value is within the bounds.
        """
        pass


@dataclass
class Range:
    """An inclusive range check.

    Attributes:
        _min: Lower bound (inclusive).
        _max: Upper bound (inclusive).
    """

    _min: Any
    _max: Any

    def check(self, val: float) -> Optional[bool]:
        """Check whether ``val`` lies within the range.

        Args:
            val: An ``int`` or ``float``, or a :class:`Comparable`.

        Returns:
            ``True`` or ``False`` for supported types. ``None`` if ``val`` is
            neither a number nor a :class:`Comparable`.
        """
        return (
            (self._min <= val <= self._max)
            if isinstance(val, (int, float))
            else (
                val.in_range(self._min, self._max)
                if isinstance(val, Comparable)
                else None
            )
        )


@dataclass
class InputChecker:
    """Declarative validation for a line of raw user input.

    Set whichever checks you need; unset checks are skipped. :meth:`check`
    tells you whether the input passes, but does **not** return the parsed
    value, so call your own conversion again once the check succeeds (see the
    example).

    Attributes:
        _type: Optional converter, called with the raw string. It must return
            ``SpecialReturnValue.INVALID_INPUT`` when the string cannot be
            converted (rather than raising). Its result is what ``_range`` is
            checked against.
        _in: Optional allow-list. The raw string must be one of these.
        not_in: Optional deny-list. The raw string must not be one of these.
        _range: Optional :class:`Range`. Checked against the converted value,
            so it requires ``_type`` to be set.
        regex: Optional compiled pattern. Must match at the start of the raw
            string (``re.Pattern.match``); end the pattern with ``$`` to
            require a full match.

    Example:
        >>> def to_int(text):
        ...     try:
        ...         return int(text)
        ...     except ValueError:
        ...         return SpecialReturnValue.INVALID_INPUT
        >>> checker = InputChecker(_type=to_int, _range=Range(1, 10))
        >>> def parse_rating(text, state):
        ...     return int(text) if checker.check(text) is True else SpecialReturnValue.INVALID_INPUT
    """

    _type: Callable[[str], Union[U, SpecialReturnValue]] = None
    _in: Optional[list[str]] = None
    not_in: Optional[list[str]] = None
    _range: Optional[Range] = None
    regex: Optional[re.Pattern] = None

    def check(self, val: str) -> Union[bool, SpecialReturnValue]:
        """Run every configured check against ``val``.

        Args:
            val: The raw input string.

        Returns:
            ``SpecialReturnValue.INVALID_INPUT`` if ``_type`` could not convert
            the string; otherwise ``True`` if all configured checks pass and
            ``False`` if any fails. Compare with ``is True`` to treat both
            failure cases the same.

        Raises:
            ValueError: If ``_range`` is set and the converted value is neither
                a number nor a :class:`Comparable`.
            UnboundLocalError: If ``_range`` is set without ``_type``, because
                there is no converted value to check.
        """
        parsed_val = None
        if self._type is not None:
            parsed_val = self._type(val)
            if parsed_val is SpecialReturnValue.INVALID_INPUT:
                return SpecialReturnValue.INVALID_INPUT

        first_check = (
            (self._in is None or val in self._in)
            and (self.not_in is None or val not in self.not_in)
            and (self.regex is None or self.regex.match(val) is not None)
        )

        if self._range is not None:
            if (
                range_check := self._range.check(
                    parsed_val if parsed_val is not None else val
                )
            ) is None:
                raise ValueError(
                    f"{parsed_val} must be of type int, float, or Comparable"
                )
        else:
            range_check = True
        return first_check and range_check
