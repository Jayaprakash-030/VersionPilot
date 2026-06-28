import urllib3

from client import pool_manager


def test_pool_manager_uses_direct_urllib3():
    assert isinstance(pool_manager(), urllib3.PoolManager)
