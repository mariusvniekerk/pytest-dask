# -*- coding: utf-8 -*-
import pytest


def test_dask_flag(testdir):
    """Make sure that pytest accepts our fixture, and runs it with dask."""

    # create a temporary pytest test module
    testdir.makepyfile("""
        def test_orwell():
            assert 2 + 2 != 5
    """)

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '--dask',
        '-v',
    )

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*::test_orwell PASSED',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


@pytest.mark.parametrize(x=list(range(10)))
def simple(x):
    assert x >= 0


def test_larger_suite(testdir):
    """Make sure that pytest accepts our fixture, and runs it with dask."""

    num_tests = 30

    # create a temporary pytest test module
    testdir.makepyfile("""
        import pytest
        
        @pytest.mark.parametrize('x', list(range({num_tests})))
        def test_param(x):
            '''a test that should take on average about 1 seconds'''
            import time
            import random
            time.sleep(random.random() * 2)
            assert x >= 0
    """.format(num_tests=num_tests))

    # run pytest with the following cmd args
    result = testdir.runpytest(
        '--dask',
        '-v',
    )

    # fnmatch_lines does an assertion internally
    runs = []
    for line in result.outlines:
        if line.startswith('test_larger_suite.py'):
            runs.append(line)

    # if we are running in parallel the chances of runs being ordered are very small. (1 / factorial(num_tests) )
    assert runs != list(sorted(runs))

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_help_message(testdir):
    result = testdir.runpytest(
        '--help',
    )
    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        'dask:',
        '*--dask*',
    ])

