"""The rules that stop automation making things worse.

These exist because every practitioner report on self-healing hits the same
problems: restart loops, flapping, and automation acting on a signal that was
never a real failure. Each guardrail below answers one of those.
"""

from collections import deque


class Guardrails:
    def __init__(self, cooldown_ticks=5, max_actions_per_window=3, window=20):
        self.cooldown_ticks = cooldown_ticks
        self.max_actions_per_window = max_actions_per_window
        self.window = window
        self._last_run = {}          # action name -> tick it last ran
        self._history = deque()      # ticks at which any action ran

    def check(self, actions, tick):
        """Return (allowed, reason). Reason is empty when allowed."""
        self._expire(tick)

        if len(self._history) + len(actions) > self.max_actions_per_window:
            return False, (f"rate limit: {len(self._history)} actions already in the "
                           f"last {self.window} ticks")

        for action in actions:
            last = self._last_run.get(action)
            if last is not None and tick - last < self.cooldown_ticks:
                return False, (f"cool-down: {action} ran {tick - last} ticks ago, "
                               f"minimum is {self.cooldown_ticks}")
        return True, ""

    def record(self, actions, tick):
        for action in actions:
            self._last_run[action] = tick
            self._history.append(tick)

    def _expire(self, tick):
        while self._history and tick - self._history[0] > self.window:
            self._history.popleft()
