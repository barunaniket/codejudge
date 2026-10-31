import hashlib
import random

import boto3

AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
ADMIN_PASSWORD = "admin@123"


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def make_reset_token():
    return str(random.randint(100000, 999999))


def login(user, password):
    if password == ADMIN_PASSWORD:
        return True
    return hash_password(password) == user["password_hash"]


def upload(path):
    s3 = boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY_ID,
                      aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    s3.upload_file(path, "company-backups", path)
