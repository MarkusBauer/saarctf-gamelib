#!/usr/bin/env python3
import functools
import math
import random
import time
import urllib.parse
import requests

from checker_utils import *
from gamelib import flag_ids
from wrapped_interface import ServiceInterfaceWrapper


def make_badge(text: str, color: str, name='checkers'):
    r = requests.get(f'https://img.shields.io/badge/{urllib.parse.quote(name)}-{urllib.parse.quote(text)}-{urllib.parse.quote(color)}')
    assert r.status_code == 200
    os.makedirs(os.path.join(BASE_DIR, 'public'), exist_ok=True)
    with open(os.path.join(BASE_DIR, 'public', f'ci-{name}.svg'), 'wb') as f:
        f.write(r.content)
    open(os.path.join(BASE_DIR, '.nobadge'), 'w').close()


def check_basic_operations(checker, team, tick=1):
    checker.initialize_team(team)
    try:
        print(f'[...] Run check_integrity(team, {tick})')
        status, msg = run_checker(checker.check_integrity, team, tick)
        assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
        print(f'[...] Run store_flags(team, {tick})')
        status, msg = run_checker(checker.store_flags, team, tick)
        assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
        print(f'[...] Run retrieve_flags(team, {tick})')
        status, msg = run_checker(checker.retrieve_flags, team, tick)
        assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
    finally:
        checker.finalize_team(team)


def check_retrieve_all(checker, team, max_tick):
    for tick in range(1, max_tick + 1):
        checker.initialize_team(team)
        try:
            print(f'[...] Run retrieve_flags(team, {tick})')
            status, msg = run_checker(checker.retrieve_flags, team, tick)
            assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
        finally:
            checker.finalize_team(team)


def check_offline(checker, team, tick):
    checker.initialize_team(team)
    try:
        print(f'[...] Run check_integrity(team, {tick})')
        status, msg = run_checker(checker.check_integrity, team, tick)
        assert status == 'OFFLINE', f'Wrong status: {status} ("{msg}")'
        print(f'[...] Run store_flags(team, {tick})')
        status, msg = run_checker(checker.store_flags, team, tick)
        assert status == 'OFFLINE', f'Wrong status: {status} ("{msg}")'
    finally:
        checker.finalize_team(team)


def checker_test(name, hint=''):
    def wrapper(test):
        @functools.wraps(test)
        def run(*args):
            from gamelib import GameLogger
            GameLogger.reset()
            print(f'\n\n\n\n===== Test "{name}" =====')
            try:
                test(*args)
                print('[OK]  ' + name)
                result = True
            except:
                traceback.print_exc()
                print('[ERR] Test failed: ' + name)
                if hint:
                    print('      ' + hint)
                result = False
            sys.stderr.flush()
            sys.stdout.flush()
            time.sleep(0.01)
            return result

        run.__setattr__('testname', name)
        return run

    return wrapper


# TESTS
@checker_test('Sanity', 'Test basic instance sanity (valid configuration, valid flag ids etc.)')
def test_sanity(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    config: ServiceConfig = instance.config
    assert len(config.name) > 1, "Please give your script a name!"
    assert config.name != 'SampleService', "Please give your script a name!"
    assert len(config.ports) >= 1, "Please give your service ports!"
    assert config.flags_per_tick >= 1, "Please give your service flags_per_tick!"
    assert config.num_payloads >= 1, "Please give your service num_payloads!"
    for flag_id_type in config.flag_ids:
        assert flag_ids.is_valid_flag_id(flag_id_type), f'Invalid flag ID type: {flag_id_type}'


@checker_test('Basic operations', 'Apply game server script with ticks 1, 2, 3.')
def test_basic_ops(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    check_basic_operations(instance, team)
    check_basic_operations(instance, team, 2)
    check_basic_operations(instance, team, 3)
    check_retrieve_all(instance, team, 3)


@checker_test('Store multiple times', 'Store flag for tick 2 (which had already been stored before)')
def test_multi_store(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    check_basic_operations(instance, team, 2)


@checker_test('Recreate instance', 'Recreates instance and retrieves flags again. Remember: global state is forbidden!')
def test_recreate(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    print('\n      Recreate instance (remember: global state is forbidden!)')
    instance = cls(instance.config)
    check_retrieve_all(instance, team, 3)


@checker_test('Negative ticks', 'Test negative ticks (which will later be used for test-runs with invalid flags')
def test_negative_ticks(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    print('\n      Test runs will use negative ticks, your script needs to deal with that...')
    check_basic_operations(instance, team, -1)
    check_basic_operations(instance, team, -2)


@checker_test('Offline test', 'Check against offline team. Remember: all your requests must have a timeout of gamelib.TIMEOUT set!')
def test_offline(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    import gamelib
    team_offline = gamelib.Team(team.id + 1, os.urandom(6).hex(), '10.213.214.215')  # lets hope no one actually uses this one
    print('\n      Check against offline team ...')
    t = time.time()
    check_offline(instance, team_offline, 1)
    t = time.time() - t
    if t > 2 * gamelib.TIMEOUT + 10:
        print(f'You took {t:.3f} seconds for a request to an offline team. That is too long.')
        raise Exception('Timeout')


@checker_test('Missing test', 'Retrieve flag from team that was never issued. Script should return FLAGMISSING.')
def test_missing(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    print('\n      Check for a flag that has never been issued ...')
    tick = -3
    instance.initialize_team(team)
    try:
        print(f'[...] Run retrieve_flags(team, {tick})')
        status, msg = run_checker(instance.retrieve_flags, team, tick)
        assert status == 'FLAGMISSING', f'Wrong status: {status} ("{msg}")'
    finally:
        instance.finalize_team(team)


@checker_test('Real-world test', 'Run gameserver script for more ticks, trying to find edge-cases')
def test_realworld(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    start = 4
    end = 20
    times = []
    print('\n      Test a few more ticks ...')
    for tick in range(start, end + 1):
        t = time.time()
        instance.initialize_team(team)
        try:
            print(f'      Simulate tick {tick} ...')
            print(f'[...] Run check_integrity(team, {tick})')
            status, msg = run_checker(instance.check_integrity, team, tick)
            assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
            print(f'[...] Run store_flags(team, {tick})')
            status, msg = run_checker(instance.store_flags, team, tick)
            assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
            print(f'[...] Run retrieve_flags(team, {tick - 1})')
            status, msg = run_checker(instance.retrieve_flags, team, tick - 1)
            assert status == 'SUCCESS', f'Wrong status: {status} ("{msg}")'
        finally:
            instance.finalize_team(team)
        times.append(time.time() - t)
        time.sleep(1)
    print(f'Average runtime: {sum(times) / len(times):6.3f} sec')
    print(f'Minimal runtime: {max(times):6.3f} sec')
    print(f'Maximal runtime: {min(times):6.3f} sec')


@checker_test('Configuration', 'Check that your flags/payloads/flag IDs match your checker script')
def test_configuration(cls: ServiceInterfaceFactory, instance: ServiceInterface, team) -> None:
    config: ServiceConfig = instance.config
    wrapper: ServiceInterfaceWrapper = ServiceInterfaceWrapper.get_wrapper(instance)
    if wrapper.num_ticks() < 10:
        print('not enough ticks ran, skipping configuration checks for now...')
        return

    # check that flags_per_tick is realistic
    flags_min, flags_max, flags_avg = wrapper.flags_per_tick()
    print(f'Flags per tick:  min {flags_min},  max {flags_max},  avg {flags_avg:.3f},  configured: {config.flags_per_tick}')
    assert flags_min <= config.flags_per_tick <= flags_max, f'Your configured flags_per_tick={config.flags_per_tick} is incorrect.'
    assert math.floor(flags_avg) <= config.flags_per_tick <= math.ceil(flags_avg), \
        f'Your configured flags_per_tick={config.flags_per_tick} is too far away from the actual flags per tick.'

    # Check that payloads is correct
    payloads = wrapper.payloads()
    print(f'flag payloads configured: {config.num_payloads}   flag payloads used: {len(payloads)}')
    if len(payloads) > 10:
        assert config.num_payloads == 0, 'For services with arbitrary/random flag payload, num_payloads must be 0'
    else:
        assert payloads == set(range(len(payloads))), f'Flag payloads must be ascending, starting with 0. Your used payloads: {payloads}'
        assert len(payloads) == config.num_payloads, f'Your num_payloads must equal the actual used payloads: {len(payloads)}'

    # Check that all Flag IDs are actually used
    used_flag_ids = wrapper.used_flag_ids()
    print(f'flag IDs configured: {config.flag_ids}   flag IDs used: {used_flag_ids}')
    for i, flag_id_type in enumerate(config.flag_ids):
        if i not in used_flag_ids:
            assert False, f'Flag ID #{i} ({flag_id_type}) is unused'


def run_unittests(cls, instance: ServiceInterface, team):
    TESTS = [
        test_sanity,
        test_basic_ops,
        test_recreate,
        test_multi_store,
        test_negative_ticks,
        test_offline,
        test_missing,
        test_realworld,
        test_configuration
    ]
    wrapper = ServiceInterfaceWrapper()
    instance = wrapper.wrap(instance)
    results = [test(cls, instance, team) for test in TESTS]
    failed = sum(1 for r in results if not r)

    print('\n\n\n==== Summary =====')
    for test, r in zip(TESTS, results):
        print('[OK]  ' if r else '[ERR] ', test.testname)
    print('\n')

    if failed > 0:
        print(f'[ERR] {failed} tests failed.')
        make_badge(f'{failed}/{len(TESTS)} failed', 'red')
        raise Exception()
    print('[OK]  ALL TESTS PASSED.')


def run_simple(cls, instance, team):
    start = 1
    end = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    times = []
    times_per_operation = {'check': 0, 'store': 0, 'retrieve': 0}
    print(f'      Testing {end} ticks ...')
    states_integrity = {}
    states_store = {}
    states_retrieve = {}
    for tick in range(start, end + 1):
        t = time.time()
        instance.initialize_team(team)
        try:
            print(f'      Simulate tick {tick} ...')
            print(f'[...] Run check_integrity(team, {tick})')
            status, msg = run_checker(instance.check_integrity, team, tick)
            states_integrity[status] = states_integrity.get(status, 0) + 1
            t2 = time.time()
            times_per_operation['check'] += t2 - t
            print(f'[...] Run store_flags(team, {tick})')
            status, msg = run_checker(instance.store_flags, team, tick)
            states_store[status] = states_store.get(status, 0) + 1
            t3 = time.time()
            times_per_operation['store'] += t3 - t2
            if tick > 1:
                print(f'[...] Run retrieve_flags(team, {tick - 1})')
                status, msg = run_checker(instance.retrieve_flags, team, tick - 1)
                states_retrieve[status] = states_retrieve.get(status, 0) + 1
            else:
                states_retrieve['SUCCESS'] = states_retrieve.get('SUCCESS', 0) + 1
            times_per_operation['retrieve'] += time.time() - t3
        finally:
            instance.finalize_team(team)
        times.append(time.time() - t)
        time.sleep(1)
    print(('[OK]  ' if states_integrity.get('SUCCESS', 0) == end else '[ERR] ') + 'Integrity checks: ' + ', '.join(
        f'{c}x{s}' for s, c in states_integrity.items()))
    print(('[OK]  ' if states_store.get('SUCCESS', 0) == end else '[ERR] ') + 'Storing flags:    ' + ', '.join(
        f'{c}x{s}' for s, c in states_store.items()))
    print(('[OK]  ' if states_retrieve.get('SUCCESS', 0) == end else '[ERR] ') + 'Retrieving flags: ' + ', '.join(
        f'{c}x{s}' for s, c in states_retrieve.items()))
    print(f'Average runtime: {sum(times) / len(times):6.3f} sec')
    print(f'Minimal runtime: {min(times):6.3f} sec')
    print(f'Maximal runtime: {max(times):6.3f} sec')
    print(
        f'Avg. time per step:  {times_per_operation["check"] / len(times):6.3f} sec check   |   {times_per_operation["store"] / len(times):6.3f} sec store   |   {times_per_operation["retrieve"] / len(times):6.3f} sec retrieve')


def main(target: str, method: str) -> None:
    # Check if any checker scripts are present
    if not (BASE_DIR / 'checkers' / 'config.toml').exists():
        print('No checkerscript found. Create a file "config.toml" in folder "checkers", content see ExampleService.')
        make_badge('not found', 'yellow')
        return
    cls, config = get_checker_class()
    config.service_id = random.randint(1, 10)
    instance = cls(config)
    print('[OK]  Checker class has been created.')

    # Target
    import gamelib
    team = gamelib.Team(random.randint(1, 1000), os.urandom(6).hex(), target)

    # Run tests
    if method == 'test':
        run_unittests(cls, instance, team)
    elif method == 'run':
        run_simple(cls, instance, team)
    else:
        raise Exception(f'Invalid method: {method}')


if __name__ == '__main__':
    """
    USAGE:
    ./test-checkerscript.py                       # unit-test checkers against docker container
    ./test-checkerscript.py <target>              # unit-test checkers against ip
    ./test-checkerscript.py <target> run [ticks]  # run checkers against ip and give summary
    """
    target = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    method = sys.argv[2] if len(sys.argv) > 2 else 'test'
    print(f'[...] Checking checkerscript against "{target}" ...')
    try:
        main(target, method)
    finally:
        shutil.rmtree(CHECKER_PACKAGES_PATH, ignore_errors=True)
