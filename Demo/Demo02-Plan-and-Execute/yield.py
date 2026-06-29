import time


def count():
    yield 1
    yield 2
    yield 3

for num in count():
    print(num)
    time.sleep(1)