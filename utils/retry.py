from functools import wraps

import itertools
import time


class StatusCodeError(Exception):
    pass


class NoOutputError(Exception):
    pass

# source: https://www.calazan.com/retry-decorator-for-python-3/


def retry(max_attempts=3):

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            attempt = 0
            for attempt in itertools.count(1):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if attempt > max_attempts - 1:
                        raise e
                    time.sleep(attempt)
        return f_retry
    return deco_retry
