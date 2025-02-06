"""
Library for GameserverScript developers. Inherit ServiceInterface.
"""

import hmac
import hashlib
import base64
import inspect
import json
import re
import struct
import os
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import requests

from . import flag_ids
from .exceptions import FlagMissingException

try:
    from saarctf_commons.config import config
    from saarctf_commons.redis import get_redis_connection

except ImportError:
    # These values / methods will later be defined by the server-side configuration
    class config:  # type: ignore[no-redef]
        SECRET_FLAG_KEY: bytes = b'\x00' * 32  # type: ignore


    import redis

    REDIS_HOST = os.environ['REDIS_HOST'] if 'REDIS_HOST' in os.environ else 'localhost'
    REDIS_DB = int(os.environ['REDIS_DB']) if 'REDIS_DB' in os.environ else 3


    def get_redis_connection() -> redis.StrictRedis:
        return redis.StrictRedis(REDIS_HOST, db=REDIS_DB)

# determines size of the flag
MAC_LENGTH = 16
FLAG_LENGTH = 24
FLAG_REGEX = re.compile(r'SAAR{[A-Za-z0-9-_]{' + str(FLAG_LENGTH // 3 * 4) + '}}')


@dataclass
class Team:
    id: int  # database team ID
    name: str  # don't rely on name - it might be dropped
    ip: str  # Vulnbox IP


@dataclass
class ServiceConfig:
    name: str
    interface_file: str
    interface_class: str
    # Set this one in your inherited class if you need FlagIDs.
    # Possible values: 'username', 'hex<number>', 'alphanum<number>', 'email', 'pattern:${username}/constant_string/${hex12}'
    flag_ids: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)  # "tcp:1234"
    num_payloads: int = 1
    flags_per_tick: float = 1
    service_id: int = 1

    @classmethod
    def from_file(cls, filename: str | Path) -> 'ServiceConfig':
        return cls.from_dict(tomllib.loads(Path(filename).read_text()))

    @classmethod
    def from_dict(cls, d: dict) -> 'ServiceConfig':
        return cls(**{field.name: d[field.name] for field in fields(cls) if field.name in d})  # type: ignore

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self.__class__)}  # type: ignore

    def with_params(self, **kwargs: Any) -> 'ServiceConfig':
        return self.__class__(**(self.to_dict() | kwargs))  # type: ignore

    def __post_init__(self) -> None:
        for flag_id in self.flag_ids:
            if ',' in flag_id:
                raise ValueError('Flag IDs with , are not supported')


class ServiceInterface(ABC):
    """
    Stateless class that interacts with a specific service. Each service has an ID and a name.
    Inherit and override: check_integrity, store_flags and retrieve_flags.
    Check out the other methods, they might show useful:
    - Get a flag you want to store
    - Search for flags and check their validity
    - Make server-side data persistent (store them to Redis)
    """

    def __init__(self, config: ServiceConfig | None = None) -> None:
        if config is None:
            config = ServiceConfig.from_file(Path(inspect.getfile(self.__class__)).parent / 'config.toml')
        self.id = config.service_id
        self.config: ServiceConfig = config

    @abstractmethod
    def check_integrity(self, team: Team, tick: int) -> None:
        """
        Do integrity checks that are not related to flags (checking the frontpage, or if exploit-relevant functions are still available)
        :param Team team:
        :param int tick:
        :raises MumbleException: Service is broken
        :raises AssertionError: Service is broken
        :raises OfflineException: Service is not reachable
        :return:
        """
        raise Exception('Override me')

    @abstractmethod
    def store_flags(self, team: Team, tick: int) -> None:
        """
        Send one or multiple flags to a given team. You can perform additional functionality checks here.
        :param Team team:
        :param int tick:
        :raises MumbleException: Service is broken
        :raises AssertionError: Service is broken
        :raises OfflineException: Service is not reachable
        :return:
        """
        raise Exception('Override me')

    @abstractmethod
    def retrieve_flags(self, team: Team, tick: int) -> None:
        """
        Retrieve all flags stored in a previous tick from a given team. You can perform additional functionality checks here.
        :param Team team:
        :param int tick: The tick in which the flags have been stored
        :raises FlagMissingException: Flag could not be retrieved
        :raises MumbleException: Service is broken
        :raises AssertionError: Service is broken
        :raises OfflineException: Service is not reachable
        :return:
        """
        raise Exception('Override me')

    def initialize_team(self, team: Team) -> None:
        """
        Called once before check/store/retrieve are issued for a team.
        Override for initialization code.
        :param team:
        :return:
        """
        pass

    def finalize_team(self, team: Team) -> None:
        """
        Called once after check/store/retrieve have been issued, even in case of exceptions or timeout.
        Override for finalization code.
        :param team:
        :return:
        """
        pass

    def store(self, team: Team, tick: int, key: str, value: Any) -> None:
        """
        Store arbitrary data for the next ticks
        :param Team team:
        :param int tick:
        :param str key:
        :param any value:
        :return:
        """
        with get_redis_connection() as redis_conn:
            redis_conn.set('services:' + self.config.name + ':' + str(team.id) + ':' + str(tick) + ':' + key, json.dumps(value))

    def load(self, team: Team, tick: int, key: str) -> Any:
        """
        Retrieve a previously stored value
        :param Team team:
        :param int tick:
        :param str key:
        :return: the previously stored value, or None
        """
        with get_redis_connection() as redis_conn:
            value = redis_conn.get('services:' + self.config.name + ':' + str(team.id) + ':' + str(tick) + ':' + key)
        if value is not None:
            return json.loads(value.decode('utf-8'))
        return value

    def load_or_flagmissing(self, team: Team, tick: int, key: str) -> Any:
        value = self.load(team, tick, key)
        if value is None:
            raise FlagMissingException('Flag never stored')
        return value

    def get_flag(self, team: Team, tick: int, payload: int = 0) -> str:
        """
        Generates the flag for this service. Flag is deterministic.
        :param Team team:
        :param int tick: The tick number this flag will be set
        :param int payload: must be >= 0 and <= 0xffff. If you don't need the payload, use (0, 1, 2, ...).
        :rtype: str
        :return: the flag
        """
        data = struct.pack('<HHHH', tick & 0xffff, team.id, self.id, payload)
        mac = hmac.new(config.SECRET_FLAG_KEY, data, hashlib.sha256).digest()[:MAC_LENGTH]
        flag = base64.b64encode(data + mac).replace(b'+', b'-').replace(b'/', b'_')
        return 'SAAR{' + flag.decode('utf-8') + '}'

    def check_flag(self, flag: str, check_team_id: int | None = None, check_stored_tick: int | None = None) \
        -> tuple[int | None, int | None, int | None, int | None]:
        """
        Check if a given flag is valid for this service, and returns the components (team-id, service-id, the tick it
        has been set and the payload bytes).

        (Optional:) Check if the flag is for this team, and stored in a given tick.
        Pass check_team_id and check_stored_tick parameters for this.

        :param str flag:
        :param int|None check_team_id: Check if the flag is from this team
        :param int|None check_stored_tick: Check if the flag has been stored in the given tick
        :rtype: (int, int, int, int)
        :return: tuple (teamid, serviceid, stored_tick, payload) or (None, None, None, None) if flag is invalid
        """
        if flag[:5] != 'SAAR{' or flag[-1] != '}':
            print('Flag "{}": invalid format'.format(flag))
            return (None, None, None, None)
        data = base64.b64decode(flag[5:-1].replace('_', '/').replace('-', '+'))
        if len(data) != FLAG_LENGTH:
            print('Flag "{}": invalid length'.format(flag))
            return (None, None, None, None)
        stored_tick, teamid, serviceid, payload = struct.unpack('<HHHH', data[:-MAC_LENGTH])
        if serviceid != self.id:
            print('Flag "{}": invalid service'.format(flag))
            return (None, None, None, None)
        mac = hmac.new(config.SECRET_FLAG_KEY, data[:-MAC_LENGTH], hashlib.sha256).digest()[:MAC_LENGTH]
        if data[-MAC_LENGTH:] != mac:
            print('Flag "{}": invalid mac'.format(flag))
            return (None, None, None, None)
        # Optional checks
        if check_team_id is not None and check_team_id != teamid:
            print('Flag "{}": invalid team'.format(flag))
            return (None, None, None, None)
        if check_stored_tick is not None and check_stored_tick & 0xffff != stored_tick:
            print('Flag "{}": invalid tick'.format(flag))
            return (None, None, None, None)
        return teamid, serviceid, stored_tick, payload

    def search_flags(self, text: str) -> set[str]:
        """
        Find all flags in a given string (no validation is done)
        :param str text:
        :return: a (possibly empty) set of all flags contained in the input
        """
        return set(FLAG_REGEX.findall(text))

    def get_flag_id(self, team: Team, tick: int, index: int = 0, **kwargs) -> str:
        """
        Generate the FlagID for the flag stored in a given tick.
        The FlagID is public from the moment the gameserver script is scheduled.
        The format must be specified in #ServiceInterface.flag_id_types, see possible types there.
        :param Team team:
        :param int tick:
        :param int index:
        :return:
        """
        flag_id_type = self.config.flag_ids[index]
        if flag_id_type == 'custom':
            with get_redis_connection() as redis_conn:
                flag_id = redis_conn.get(f'custom_flag_ids:{self.config.service_id}:{tick}:{team.id}:{index}')
                if flag_id is None:
                    raise FlagMissingException('Flag ID never generated')
                return flag_id

        return flag_ids.generate_flag_id(flag_id_type, self.id, team.id, tick, index, **kwargs)

    def set_flag_id(self, team: Team, tick: int, index: int, value: str) -> None:
        if self.config.flag_ids[index] != 'custom':
            raise Exception('Cannot store into a non-custom flag ID')
        with get_redis_connection() as redis_conn:
            redis_conn.set(f'custom_flag_ids:{self.config.service_id}:{tick}:{team.id}:{index}', value)


# === Assertion methods ===

def assert_equals(expected, result) -> None:
    """
    :param expected:
    :param result:
    :return: Raises an AssertionError if expected != result
    """
    if expected != result:
        raise AssertionError("Expected {} but was {}".format(repr(expected), repr(result)))


def assert_requests_response(resp, contenttype: str = 'application/json; charset=utf-8') -> requests.Response:
    """
    :param requests.Response resp:
    :param str contenttype:
    :return: Assert that a request was answered with statuscode 200 and a given content-type
    """
    if resp.status_code != 200:
        print('Response =', resp)
        print('Url =', resp.url)
        print('---Response---\n' + resp.text[:4096] + '\n\n')
        raise AssertionError('Invalid status code {} (text: "{}")'.format(resp.status_code, resp.text[:512]))
    assert_equals(contenttype.lower(), resp.headers['Content-Type'].lower())
    return resp
