import os
import subprocess


def ping_host(host):
    # Lets admins check if a server is reachable
    return os.system("ping -c 1 " + host)


def archive_folder(folder_name):
    cmd = f"tar -czf backup.tar.gz {folder_name}"
    subprocess.call(cmd, shell=True)


def calculator(expression):
    # expression comes straight from the web form
    return eval(expression)


if __name__ == "__main__":
    target = input("Host to ping: ")
    ping_host(target)
    print(calculator(input("Expression: ")))
