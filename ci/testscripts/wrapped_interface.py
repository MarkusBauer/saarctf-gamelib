import functools
import sys
from pathlib import Path
from typing import Any, cast, TypeVar, ParamSpec, Callable

# make "import gamelib" possible
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from gamelib import ServiceInterface, Team

T = TypeVar('T')
P = ParamSpec('P')


def prefix_function(prefix: Callable[P, None], func: Callable[P, T]) -> Callable[P, T]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs):
        prefix(*args, **kwargs)
        return func(*args, **kwargs)

    return wrapper


class ServiceInterfaceWrapper:
    def __init__(self) -> None:
        self._requested_flags: set[tuple[int, int, int]] = set()
        self._requested_flag_ids: set[tuple[int, int, int]] = set()
        self._runned_ticks: set[tuple[int, int]] = set()

    def wrap(self, iface: ServiceInterface) -> ServiceInterface:
        if hasattr(iface, '_service_wrapper'):
            return iface
        iface.get_flag = prefix_function(self._get_flag, iface.get_flag)
        iface.get_flag_id = prefix_function(self._get_flag_id, iface.get_flag_id)
        iface.check_integrity = prefix_function(self._record_tick, iface.check_integrity)
        iface.store_flags = prefix_function(self._record_tick, iface.store_flags)
        iface.retrieve_flags = prefix_function(self._record_tick, iface.retrieve_flags)
        setattr(iface, '_service_wrapper', self)
        return iface

    @classmethod
    def get_wrapper(cls, iface: ServiceInterface) -> 'ServiceInterfaceWrapper':
        return getattr(iface, '_service_wrapper')

    def _get_flag(self, team: Team, tick: int, payload: int = 0) -> None:
        self._requested_flags.add((team.id, tick, payload))

    def _get_flag_id(self, team: Team, tick: int, index: int = 0, **kwargs) -> None:
        self._requested_flag_ids.add((team.id, tick, index))

    def _record_tick(self, team: Team, tick: int) -> None:
        self._runned_ticks.add((team.id, tick))

    def used_flag_ids(self) -> set[int]:
        return set(index for _, _, index in self._requested_flag_ids)

    def flags_per_tick(self) -> tuple[int, int, float]:
        counts = {}
        for team_id, tick, payload in self._requested_flags:
            if tick >= 0:
                counts[(team_id, tick)] = counts.get((team_id, tick), 0) + 1
        return min(counts.values()), max(counts.values()), sum(counts.values()) / len(counts)

    def payloads(self) -> set[int]:
        return set(payload for _, _, payload in self._requested_flags)

    def num_ticks(self) -> int:
        return len(self._runned_ticks)
