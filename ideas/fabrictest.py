from fabric import Connection

result = Connection('35.227.158.60')
# connect_kwargs={'passphrase': passphrase})

print(result.run('echo "Hello remote world"'))
print(dir(result.run('')))

# Copies file
print(result.put('./watchdog_test.py', remote='/home/adryw/test_wow/'))
