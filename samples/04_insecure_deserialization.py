import pickle
import socket

import yaml


def load_config(path):
    with open(path) as f:
        return yaml.load(f, Loader=yaml.Loader)


def receive_job(port=9000):
    server = socket.socket()
    server.bind(("0.0.0.0", port))
    server.listen(1)
    conn, _ = server.accept()
    data = conn.recv(65536)
    job = pickle.loads(data)
    return job.run()


def read_user_file(filename):
    with open("/var/app/uploads/" + filename) as f:
        return f.read()
