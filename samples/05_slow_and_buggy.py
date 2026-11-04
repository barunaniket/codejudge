def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j] and items[i] not in duplicates:
                duplicates.append(items[i])
    return duplicates


def build_report(records):
    report = ""
    for r in records:
        report = report + str(r["name"]) + "," + str(r["score"]) + "\n"
    return report


def average(scores):
    return sum(scores) / len(scores)


def count_errors(log_paths):
    total = 0
    for path in log_paths:
        f = open(path)
        for line in f.readlines():
            if "ERROR" in line:
                total += 1
    return total


def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags


def parse_age(value):
    try:
        return int(value)
    except:
        pass
