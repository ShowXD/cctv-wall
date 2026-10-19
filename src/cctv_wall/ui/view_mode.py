"""Which chrome the wall shows, as one immutable value instead of scattered flags.

Every transition returns a new ViewMode, so the rules can be tested without Qt.
Applying one to real widgets is the window's job.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class ViewMode:
    """Immersive state, plus what to restore when leaving it."""

    fullscreen: bool = False
    filled: bool = False
    was_maximized: bool = False

    @property
    def chrome_visible(self) -> bool:
        return not (self.fullscreen or self.filled)

    @property
    def grips_visible(self) -> bool:
        return self.filled and not self.fullscreen

    def enter_fullscreen(self, was_maximized: bool) -> "ViewMode":
        return replace(self, fullscreen=True, was_maximized=was_maximized)

    def exit_fullscreen(self) -> "ViewMode":
        return replace(self, fullscreen=False)

    def toggle_filled(self) -> "ViewMode":
        return replace(self, filled=not self.filled)
