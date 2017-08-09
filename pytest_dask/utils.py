
def get_imports():
    import sys
    return sys.path


def update_syspath(syspath):
    import sys
    for p in reversed(syspath):
        if p not in sys.path:
            sys.path.insert(0, p)
    return sys.path


def restore_syspath(syspath):
    import sys
    sys.path[:] = syspath
    return sys.path
