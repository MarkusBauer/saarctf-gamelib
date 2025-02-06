import hashlib
import hmac
import random
import re
import string

try:
    from saarctf_commons.config import config
except ImportError:
    # These values / methods will later be defined by the server-side configuration
    class config:  # type: ignore[no-redef]
        SECRET_FLAG_KEY: bytes = b"\x00" * 32  # type: ignore


def generate_flag_id(
    flag_id_type: str,
    service_id: int,
    team_id: int,
    tick: int,
    index: int = 0,
    **kwargs,
) -> str:
    """
    Generate FlagID for a flag stored in a given tick at a given team and service.
    The FlagID is public from the moment the gameserver script is scheduled.
    The format must be specified in ServiceInterface.flag_id_types,
    see possible types in `generate_flag_id_rnd` (below).
    """
    seed = hmac.new(
        config.SECRET_FLAG_KEY,
        f"{service_id}|{team_id}|{tick}|{index}".encode(),
        hashlib.sha1,
    ).digest()
    rnd = random.Random(seed)
    return generate_flag_id_rnd(flag_id_type, rnd, **kwargs)


def generate_flag_id_rnd(flag_id_type: str, rnd: random.Random, **kwargs) -> str:
    """
    Generate a flag id. Available types:

    username: A username
      Example: "username" -> "AbsentOrganicInlaws3828"
    hex<len>: hex chars (lowercase and digit). len in DECIMAL:
      Example: "hex10" -> "36b43798b7"
    alphanum<len>: Lowercase, uppercase, digit
      Example: "alphanum10" -> "naBUXUv7py"
    email: As the name suggests...
      Example: "email" -> "slipperybite2396@crowdedseriousduststorm467.com"
    choose_k_from:<len>:<alphabet>: Choose k times from alphabet
      Example: "choose_k_from:10:123,:-" -> "--2:,1-,:-"
    pattern:<pattern>: Combine all other types in a pattern
      Example: "pattern:${hex4}_${username}" -> "cd3b_BewilderedAlcoholicBamboo2250"
    """
    if flag_id_type == "username":
        # conditional import because the file is massive
        from . import usernames

        return usernames.generate_username(generator=rnd, **kwargs)
    elif flag_id_type.startswith("hex"):
        length = int(flag_id_type.removeprefix("hex"))
        return "".join(rnd.choices(string.digits + "abcde", k=length))
    elif flag_id_type.startswith("alphanum"):
        length = int(flag_id_type.removeprefix("alphanum"))
        return "".join(
            rnd.choice(string.ascii_letters + string.digits) for _ in range(length)
        )
    elif flag_id_type == "email":
        # conditional import because the file is massive
        from . import usernames

        return (
            usernames.generate_username(generator=rnd, camelcase=False, **kwargs)
            + "@"
            + usernames.generate_username(generator=rnd, camelcase=False, **kwargs)
            + ".com"
        )
    elif flag_id_type.startswith("choose_k_from:"):
        _, k, alpha = flag_id_type.split(":", maxsplit=2)
        return "".join(rnd.choices(alpha, k=int(k)))
    elif flag_id_type.startswith("pattern:"):
        pattern = flag_id_type.removeprefix("pattern:")
        return re.sub(
            r"\$\{(.*?)}",
            lambda m: generate_flag_id_rnd(m.group(1), rnd, **kwargs),
            pattern,
        )
    else:
        raise ValueError(f"Invalid FlagId type requested: {repr(flag_id_type)}")


def is_generatable_flag_id(flag_id_type: str) -> bool:
    try:
        generate_flag_id(flag_id_type, 1, 1, 1)
        return True
    except ValueError:
        return False


def is_valid_flag_id(flag_id_type: str) -> bool:
    return flag_id_type == 'custom' or is_generatable_flag_id(flag_id_type)
