import importlib
import os
import re
import shutil
import sys
import traceback
from pathlib import Path
from types import ModuleType
from typing import Callable, TypeAlias

import timeout_decorator

# make "import gamelib" possible
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from gamelib import ServiceConfig, ServiceInterface
from gamelib.exceptions import handle_checker_exceptions

BASE_DIR: Path = Path(os.getcwd()).absolute()

CHECKER_PACKAGES_PATH: Path = Path('/dev/shm/' + os.urandom(8).hex())
PACKAGE = os.urandom(8).hex()
FULL_PACKAGE_PATH = CHECKER_PACKAGES_PATH / PACKAGE
sys.path.append(str(CHECKER_PACKAGES_PATH))

ignore_patterns = [
    re.compile(r'^__pycache__$'),
    re.compile(r'\.pyc$'),
    re.compile(r'^\.idea$'),
    re.compile(r'^\.git'),
    re.compile(r'^\.mypy_cache$'),
    re.compile(r'^gamelib$')
]

ServiceInterfaceFactory: TypeAlias = Callable[[ServiceConfig], ServiceInterface]


def is_ignored(folder: str) -> bool:
    return any(p.match(folder) for p in ignore_patterns)


def create_package(folder: Path) -> None:
    # Code is basically a mocked copy of the DB-Filesystem code from the gameserver.
    os.makedirs(FULL_PACKAGE_PATH, exist_ok=True)
    for root, subdirs, files in os.walk(folder, followlinks=True):
        # add directories
        subdirs[:] = [dir for dir in subdirs if not is_ignored(dir)]
        for dir in subdirs:
            path = dir if root == folder else str(Path(root).relative_to(folder) / dir)
            os.makedirs(os.path.join(FULL_PACKAGE_PATH, path), exist_ok=True)

        # add files
        for file in files:
            if is_ignored(file):
                continue
            fname = root + '/' + file
            path = file if root == folder else str(Path(root).relative_to(folder) / file)
            shutil.copy(fname, os.path.join(FULL_PACKAGE_PATH, path))

    # Find and link gamelib
    if os.path.exists(BASE_DIR / 'gamelib'):
        os.symlink(BASE_DIR / 'gamelib', CHECKER_PACKAGES_PATH / 'gamelib')
    elif os.path.exists(BASE_DIR / 'checkers' / 'gamelib'):
        os.symlink(BASE_DIR / 'checkers' / 'gamelib', CHECKER_PACKAGES_PATH / 'gamelib')
    elif os.path.exists(BASE_DIR / 'ci' / 'service-scripts' / 'gamelib'):
        os.symlink(BASE_DIR / 'ci' / 'service-scripts' / 'gamelib', CHECKER_PACKAGES_PATH / 'gamelib')
    else:
        raise Exception('gamelib not found!')

    print(f'[OK]  Created package {FULL_PACKAGE_PATH}')


def import_module_from_package(filename: str) -> ModuleType:
    modulename = '{}.{}'.format(PACKAGE, filename.replace('.py', '').replace('/', '.'))
    spec = importlib.util.spec_from_file_location(modulename, FULL_PACKAGE_PATH / filename)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise Exception('Loader is not present')
    try:
        spec.loader.exec_module(module)  # type: ignore
    except ImportError:
        print('=== IMPORT ERROR ===')
        print('Remember: ')
        print('1. Only use relative imports (with dot) for your own script files:   import .my_other_python_file')
        print('2. If you need additional libraries for your script (not in requirements-checker), report them to the orgas.')
        raise
    print('[OK]  PackageLoader imported {}'.format(modulename))
    return module


def get_checker_class() -> tuple[ServiceInterfaceFactory, ServiceConfig]:
    # Find checkerfile
    config = ServiceConfig.from_file(BASE_DIR / 'checkers' / 'config.toml')
    # Create package
    create_package(BASE_DIR / 'checkers')
    # Import checkerscript
    module = import_module_from_package(config.interface_file)
    return getattr(module, config.interface_class), config


@timeout_decorator.timeout(30)
def run_checker(func, team, tick) -> tuple[str, str | None]:
    try:
        return handle_checker_exceptions(lambda: func(team, tick))
    except:
        traceback.print_exc()
        return 'CRASHED', None
