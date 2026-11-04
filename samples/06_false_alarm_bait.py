"""Quiz utilities. Static tools flag several lines here that are actually safe."""
import random
import subprocess

QUESTIONS = ["What is 2+2?", "Capital of France?", "Largest planet?"]


def shuffled_quiz():
    # random is fine here: shuffling quiz order is not security sensitive
    order = QUESTIONS[:]
    random.shuffle(order)
    return order


def git_version():
    # constant argument list, no shell, no user input
    out = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def password_field_label():
    password_label = "Password"
    return password_label


def test_shuffle_keeps_all_questions():
    assert sorted(shuffled_quiz()) == sorted(QUESTIONS)
