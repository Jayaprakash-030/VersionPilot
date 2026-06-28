import urllib3


def pool_manager():
    return urllib3.PoolManager()
