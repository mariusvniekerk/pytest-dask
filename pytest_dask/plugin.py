# -*- coding: utf-8 -*-


import pytest
from _pytest.runner import CallInfo
from distributed import Client, LocalCluster, as_completed
from contextlib import contextmanager
import sys

# Ensure that the serializer is pathched appropriately.
from pytest_dask.serde_patch import *  # noqa: F401,F403
from pytest_dask.utils import get_imports, update_syspath, restore_syspath

from logging import getLogger
logger = getLogger(__name__)


class DaskRunner(object):
    def __init__(self, config):
        self.config = config
        self.scheduler_mode = config.getvalue("dask_scheduler_mode")
        remote_cluster_address = config.getvalue('dask_scheduler_address')
        if remote_cluster_address:
            self.client = Client(remote_cluster_address)
        else:
            self.cluster = LocalCluster(
                ip='127.0.0.1',
                n_workers=int(config.getvalue('dask_nworkers')),
                processes=config.getvalue('dask_scheduler_mode') == 'process'
            )
            self.client = Client(self.cluster, set_as_default=True)

    def __getstate__(self):
        return {'config': None}

    def __setstate__(self, state):
        for k in state:
            pass

    def pytest_runtestloop(self, session):
        if (session.testsfailed and
                not session.config.option.continue_on_collection_errors):
            raise session.Interrupted(
                "%d errors during collection" % session.testsfailed)

        unregister_plugins = ['debugging', 'terminalreporter']
        for p in unregister_plugins:
            session.config.pluginmanager.unregister(p)

        if session.config.option.collectonly:
            return True

        def generate_tasks(session):
            for i, item in enumerate(session.items):

                # @delayed(pure=False)
                def run_test(_item):
                    # ensure that the plugin manager gets recreated appropriately.
                    _item.config.pluginmanager.__recreate__()
                    results = self.pytest_runtest_protocol(item=_item, nextitem=None)
                    return results

                # hook = item.ihook
                # try to ensure that the module gets treated as a dynamic module that does not
                # exist.

                # delattr(item.module, '__file__')
                # setup = hook.pytest_runtest_setup
                # make_report = hook.pytest_runtest_makereport

                fut = self.client.submit(run_test, item, pure=False)
                yield fut

        with self.remote_syspath_ctx():
            tasks = generate_tasks(session)

            # log these reports to the console.
            for resolved in as_completed(tasks):
                t = resolved.result()
                for report in t:
                    session.ihook.pytest_runtest_logreport(report=report)

        return True

    @contextmanager
    def remote_syspath_ctx(self):
        # Due to test directories being dynamic in certain cases we should make sure that our
        # workers are using the same pythonpath that we are using here.
        original_sys_path = self.client.run(get_imports)
        logger.debug("Original remote sys path %s", original_sys_path)
        updated_sys_path = self.client.run(update_syspath, sys.path)
        logger.debug("Updated remote sys path %s", updated_sys_path)
        try:
            yield
        finally:
            # restore correct syspath
            for worker, value in original_sys_path.items():
                self.client.run(restore_syspath, value, workers=[worker])

            original_sys_path2 = self.client.run(get_imports)
            assert original_sys_path == original_sys_path2

    def call_and_report(self, item, when, log=True, **kwds):
        call = self.call_runtest_hook(item, when, **kwds)
        hook = item.ihook
        report = hook.pytest_runtest_makereport(item=item, call=call)
        return report

    def call_runtest_hook(self, item, when, **kwds):
        hookname = "pytest_runtest_" + when
        ihook = getattr(item.ihook, hookname)
        return CallInfo(lambda: ihook(item=item, **kwds), when=when)

    # VENDORED so that we have access to the report objects and not just T/F
    def pytest_runtest_protocol(self, item, log=True, nextitem=None):
        hasrequest = hasattr(item, "_request")
        if hasrequest and not item._request:
            item._initrequest()
        rep = self.call_and_report(item, "setup", log)
        reports = [rep]
        if rep.passed:
            if item.config.option.setupshow:
                # TODO figure out how to pass this test
                # show_test_item(item)
                pass
            if not item.config.option.setuponly:
                rep = self.call_and_report(item, "call", log)
                reports.append(rep)
        rep = self.call_and_report(item, "teardown", log, nextitem=None)
        reports.append(rep)
        # after all teardown hooks have been called
        # want funcargs and request info to go away
        if hasrequest:
            item._request = False
            item.funcargs = None
        return reports

    def pytest_runtest_setup(self, item):
        item.session._setupstate.prepare(item)

    def pytest_unconfigure(self, config):
        """ called before test process is exited.  """
        if hasattr(self, 'cluster'):
            self.cluster.close()


def pytest_addoption(parser):
    group = parser.getgroup('dask')
    group.addoption(
        '--dask',
        action='store_true',
        dest='dask',
        default=False,
        help='Set the value for the fixture "dask".',
    )

    group.addoption(
        '--dask-scheduler-address',
        dest='dask_scheduler_address',
        default='',
        help='(optional) specify an existing dask scheduler to connect to.',
    )

    group.addoption(
        '--dask-scheduler-mode',
        type='choice',
        choices=['thread', 'process'],
        default='process',
        help='which parallism method should be employed',
    )

    group.addoption(
        '--dask-test-selection',
        type='choice',
        choices=['all', 'marked'],
        default='all',
    )

    group.addoption(
        '--dask-nworkers',
        type='int',
        default='4',
    )


@pytest.mark.trylast
def pytest_configure(config):
    if config.getoption("dask"):
        dask_session = DaskRunner(config)
        config.pluginmanager.register(dask_session, "dask_session")
