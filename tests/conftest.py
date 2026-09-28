import pytest

from campus.config import Config
from campus.store import Store


@pytest.fixture
def config(tmp_path):
    result = Config(home=tmp_path / "campus")
    result.initialize()
    return result


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "test.sqlite3")
    yield result
    result.close()
