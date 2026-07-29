"""FSM states for multi-turn interactions."""

from aiogram.fsm.state import State, StatesGroup


class MonthlyStates(StatesGroup):
    """Monthly report states."""
    waiting_reformulation = State()


class RecallStates(StatesGroup):
    """Vault search states."""
    waiting_query = State()
