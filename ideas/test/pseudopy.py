import time
print('This was written on remote, is it working on local?')

if __name__ == '__main__':
    print('Main')

    t = time.time()

    time.sleep(1)

    print(time.time() - t)
