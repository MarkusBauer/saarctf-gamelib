import os
import random
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Any, ClassVar

import requests

try:
    os.environ['PWNLIB_NOTERM'] = '1'
    from pwnlib.tubes.tube import tube  # type: ignore
    from pwnlib.tubes.remote import remote  # type: ignore
except ImportError:
    print('pwntools not available!')
    tube = Any

# default timeout for a single connection
TIMEOUT = 7


class Session(requests.Session):
    """
    USAGE:
    use Session() instead of requests.Session():
    session = Session()
    response = session.get(...)
    """

    user_agents: ClassVar[list[str] | None] = None

    def __init__(self):
        super().__init__()
        if self.user_agents is None:
            self._load_user_agents()
        if len(self.user_agents) > 0:
            self.headers['User-Agent'] = random.choice(self.user_agents)

    def request(self, method: str | bytes, url: str | bytes, *args: Any, **kwargs: Any) -> requests.Response:
        if 'timeout' not in kwargs:
            kwargs['timeout'] = TIMEOUT

        silent = kwargs.pop('silent', False)
        if not silent:
            opts = {}
            if 'params' in kwargs:
                opts['params'] = kwargs['params']
            print(f'> {method!s} {url!s} {opts}')

        response = super().request(method, url, *args, **kwargs)

        if not silent:
            print(f'< [{response.status_code}] {len(response.content)} bytes')

        return response

    @classmethod
    def _load_user_agents(cls) -> None:
        agents = []
        for path in (Path('user-agents.txt'), Path.home() / 'user-agents.txt', Path('/usr/share/user-agents.txt')):
            try:
                agents = [a.strip() for a in path.read_text().split('\n') if a.strip()]
                break
            except (FileNotFoundError, PermissionError):
                pass
        cls.user_agents = agents


@contextmanager
def remote_connection(host: str, port: int, **kwargs) -> Generator[tube, None, None]:
    """
    USAGE:

    with remote_connection(team.ip, 12345) as conn:
        conn.recv_line()  # conn is a simple pwnlib tube

    :param host:
    :param port:
    :return: a context manager that yields a connection (like pwntools remote)
    """
    connection = remote(host, port, timeout=TIMEOUT, **kwargs)
    try:
        yield connection
    finally:
        connection.close()
