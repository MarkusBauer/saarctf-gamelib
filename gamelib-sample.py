import sys
import requests

from gamelib import *


class SampleServiceInterface(ServiceInterface):
    def check_integrity(self, team: Team, tick: int) -> None:
        try:
            # use gamelib.Session() instead of plain requests!
            assert_requests_response(Session().get(f'http://{team.ip}:8000/'), 'text/html; charset=utf-8')
        except IOError:
            raise OfflineException('Could not login')

    def store_flags(self, team: Team, tick: int) -> None:
        username = usernames.generate_username()
        password = usernames.generate_password()
        self.store(team, tick, 'credentials', [username, password])

        try:
            flag = self.get_flag(team, tick, 1)
            response = assert_requests_response(
                Session().post(f'http://{team.ip}:8000/register', data={'username': username, 'password': password, 'flag': flag}),
                'text/html; charset=utf-8'
            )
            assert 'Flag stored!' in response.text
        except IOError:
            raise OfflineException('Could not register')

    def retrieve_flags(self, team: Team, tick: int) -> None:
        username, password = self.load(team, tick, 'credentials')
        try:
            session = Session()
            assert_requests_response(
                session.post(f'http://{team.ip}:8000/login', data={'username': username, 'password': password}),
                'text/html; charset=utf-8'
            )

            response = assert_requests_response(session.get(f'http://{team.ip}:8000/data'), 'text/html; charset=utf-8')
            # V1 - easy check for flag
            flag = self.get_flag(team, tick, 1)
            if flag not in response.text:
                raise FlagMissingException("Flag not found")

            # V2 - advanced check with payload
            flags = self.search_flags(response.text)
            assert len(flags) > 0, 'No flags found'
            flag = list(flags)[0]
            _, _, _, payload = self.check_flag(flag, team.id, tick)  # returns None,None,None,None if invalid
            if not flag or not payload or payload != 1:
                # not the flag we're looking for
                raise FlagMissingException("Flag not found")

        except IOError:
            raise OfflineException('Could not login')


if __name__ == '__main__':
    # TEST CODE
    team = Team(12, 'n00bs', '127.0.0.1')
    service = SampleServiceInterface()

    if len(sys.argv) > 2 and sys.argv[2] == 'retrieve':
        for tick in range(1, 10):
            try:
                service.retrieve_flags(team, tick)
            except:
                pass
        sys.exit(0)
    elif len(sys.argv) > 2 and sys.argv[2] == 'store':
        for tick in range(50, 55):
            try:
                service.store_flags(team, tick)
            except:
                pass
        sys.exit(0)

    for tick in range(1, 4):
        print(f'\n\n=== TICK {tick} ===')
        service.check_integrity(team, tick)
        service.store_flags(team, tick)
        service.retrieve_flags(team, tick)
