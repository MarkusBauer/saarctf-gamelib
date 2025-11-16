import os
import random
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Any, ClassVar
from urllib.parse import urlparse

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
    use gamelib.Session() instead of requests.Session():
    session = Session()
    response = session.get(...)
    """

    user_agents: ClassVar[list[str] | None] = None

    def __init__(self) -> None:
        super().__init__()
        if self.user_agents is None:
            self._load_user_agents()
        if self.user_agents:
            self.headers['User-Agent'] = random.choice(self.user_agents)
        # False = follow redirects within the service (default), True = follow redirects to other services/external hosts
        self.follow_external_redirects: bool = False

    def request(self, method: str | bytes, url: str | bytes, *args: Any, **kwargs: Any) -> requests.Response:
        if 'timeout' not in kwargs:
            kwargs['timeout'] = TIMEOUT

        silent = kwargs.pop('silent', False)
        if not silent:
            opts = {}
            if 'params' in kwargs:
                opts['params'] = kwargs['params']
            if opts:
                print(f'> {method!s} {url!s} {opts}')
            else:
                print(f'> {method!s} {url!s}')

        response = super().request(method, url, *args, **kwargs)

        if not silent:
            for intermediate in response.history:
                print(f'< [{intermediate.status_code}] {intermediate.headers.get('location', '???')}')
            print(f'< [{response.status_code}] {len(response.content)} bytes')

        return response

    @classmethod
    def _load_user_agents(cls) -> list[str]:
        agents = []
        for path in (Path('user-agents.txt'), Path.home() / 'user-agents.txt', Path('/usr/share/user-agents.txt')):
            try:
                agents = [a.strip() for a in path.read_text().split('\n') if a.strip()]
                break
            except (FileNotFoundError, PermissionError):
                pass
        cls.user_agents = agents
        return agents

    def get_redirect_target(self, resp: requests.Response) -> str | None:
        new_url = super().get_redirect_target(resp)
        if not self.follow_external_redirects and new_url:
            # do not follow redirects to other domains/IPs/hosts/anything outside the network
            old_parsed = urlparse(resp.url)
            new_parsed = urlparse(new_url)
            if old_parsed.hostname != new_parsed.hostname and new_parsed.netloc != '':
                print(f'  ... not following redirect from {old_parsed.hostname!r} to {new_url!r}')
                return None
        return new_url


@contextmanager
def remote_connection(host: str, port: int, **kwargs: Any) -> Generator[tube, None, None]:
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
