import requests.packages.urllib3 as urllib3


def pool_manager():
    return urllib3.PoolManager()
