import traceback
from contextlib import contextmanager
from typing import Iterator, Callable


class CheckerException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message

    def __str__(self) -> str:
        return str(self.message)


class FlagMissingException(CheckerException):
    """
    Service is working, but flag could not be retrieved
    """
    pass


class MumbleException(CheckerException):
    """
    Service is online, but behaving unexpectedly (dropping data, returning wrong answers, ...). AssertionError is also valid.
    """
    pass


class OfflineException(CheckerException):
    """
    Service is not reachable / connections get dropped or interrupted
    """
    pass


@contextmanager
def translate_checker_exceptions() -> Iterator[None]:
    import requests
    import pwnlib.exception

    try:
        yield

    # assertions to mumble
    except AssertionError as e:
        raise MumbleException(str(e) + ' ' + repr(e.args)) from e

    # various key/value/index errors to mumble
    except (KeyError, ValueError, IndexError) as e:
        raise MumbleException(str(e)) from e

    # invalid HTTP requests
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError, requests.exceptions.TooManyRedirects) as e:
        raise MumbleException(str(e)) from e

    # various connection errors
    except (ConnectionError, EOFError) as e:
        raise OfflineException(str(e)) from e
    except (requests.ConnectionError, requests.exceptions.Timeout) as e:
        raise OfflineException(str(e)) from e
    except pwnlib.exception.PwnlibException as e:
        if 'Could not connect to' in e.args[0]:
            raise OfflineException(str(e.args[0])) from e
        raise
    except TimeoutError as e:
        # we just guess that timeouts appear on connection attempts
        raise OfflineException(str(e)) from e
    except OSError as e:
        if 'No route to host' in str(e):
            raise OfflineException('no route to host')
        raise


def handle_checker_exceptions(c: Callable[[], tuple[str, str | None] | None]) -> tuple[str, str | None]:
    try:
        with translate_checker_exceptions():
            result = c()
            return result if result is not None else ('SUCCESS', None)

    except FlagMissingException as e:
        traceback.print_exc()
        return 'FLAGMISSING', e.message
    except MumbleException as e:
        traceback.print_exc()
        return 'MUMBLE', e.message
    except OfflineException as e:
        traceback.print_exc()
        return 'OFFLINE', e.message
