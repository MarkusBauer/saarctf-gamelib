import os
from contextlib import contextmanager
from typing import Generator, Any

import requests
try:
    os.environ['PWNLIB_NOTERM'] = '1'
    from pwnlib.tubes.tube import tube
    from pwnlib.tubes.remote import remote
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

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        if 'timeout' not in kwargs:
            kwargs['timeout'] = TIMEOUT

        silent = kwargs.pop('silent', False)
        if not silent:
            opts = {}
            if 'params' in kwargs:
                opts['params'] = kwargs['params']
            print(f'> {method} {url} {opts}')

        response = super().request(method, url, **kwargs)

        if not silent:
            print(f'< [{response.status_code}] {len(response.content)} bytes')

        return response


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
