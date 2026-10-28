"""Every application SQL statement is PREPAREd (parsed, name-resolved and
type-checked) against a real PostgreSQL database built from the schema.
This catches wrong column names and type errors in the unexecuted API
layer before deployment."""
import re

import pytest

from app.repo.queries import Q
from tests.sql.pg import drop_db, fresh_db

PARAM = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")


def to_positional(sql: str) -> str:
    names: dict[str, int] = {}

    def repl(m):
        n = m.group(1)
        if n not in names:
            names[n] = len(names) + 1
        return f"${names[n]}"
    return PARAM.sub(repl, sql)


@pytest.fixture(scope="module")
def db():
    d = fresh_db()
    yield d
    drop_db(d)


@pytest.mark.parametrize("name", sorted(Q))
def test_query_prepares(db, name):
    stmt = f"q_{name}"
    res = db.run(f"PREPARE {stmt} AS {to_positional(Q[name])}; DEALLOCATE {stmt};", check=False)
    assert res.returncode == 0, f"{name}: {res.stderr.strip()}"
