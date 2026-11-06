"""Deterministic balanced primary owners, independent of saved grades and ratings."""
from collections import Counter, defaultdict


def balanced_owners(teacher_ids, keys, completed=None, groups=None):
    """Return one primary owner per key with workloads differing by at most one.

    Prefer the existing reviewer wherever capacity permits. Reviewers with fewer
    completed tasks get first choice when earlier reviews overlap. Extra reviews
    remain history; this function never modifies or discards them.
    """
    teachers, tasks = list(teacher_ids), list(keys)
    if not teachers or len(set(teachers)) != len(teachers):
        raise ValueError('Provide distinct teachers in roster order.')
    if len(set(tasks)) != len(tasks):
        raise ValueError('Task keys must be distinct.')
    completed, groups = completed or {}, groups or {}
    base, extra = divmod(len(tasks), len(teachers))
    quotas = {teacher: base + (index < extra) for index, teacher in enumerate(teachers)}
    positions = {teacher: index for index, teacher in enumerate(teachers)}
    load, group_load = Counter(), defaultdict(Counter)
    owners = {}
    preferred = {teacher: [key for key in tasks if teacher in completed.get(key, ())]
                 for teacher in teachers}

    def assign(key, teacher):
        owners[key] = teacher
        load[teacher] += 1
        group_load[teacher][groups.get(key)] += 1

    # Scarce existing reviews take priority over a teacher with many prior reviews.
    for teacher in sorted(teachers, key=lambda user: (len(preferred[user]), positions[user])):
        for key in preferred[teacher]:
            if key not in owners and load[teacher] < quotas[teacher]:
                assign(key, teacher)

    for key in tasks:
        if key in owners:
            continue
        candidates = [teacher for teacher in teachers if load[teacher] < quotas[teacher]]
        teacher = min(candidates, key=lambda user: (
            load[user], group_load[user][groups.get(key)], positions[user]))
        assign(key, teacher)
    return owners
