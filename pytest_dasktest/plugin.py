# -*- coding: utf-8 -*-


import pytest

from _pytest.runner import CallInfo
from dask import compute, delayed
from distributed import Client, LocalCluster


# Ensure that the serializer is pathched appropriately.
from pytest_dasktest.serde_patch import *



class DaskRunner(object):
    def __init__(self, config):
        self.config = config
        self.cluster = LocalCluster(n_workers=1, processes=False)
        self.client = Client(self.cluster, set_as_default=True)

    def __getstate__(self):
        return {'config': self.config}

    def __setstate__(self, state):
        setattr(self, 'config', state['config'])

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

        def generate_tasks():
            for i, item in enumerate(session.items):
                # nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
                @delayed
                def run_test(item):
                    # for p in unregister_plugins:
                    #     item.config.pluginmanager.unregister(p)
                    new_pm = item.config.pluginmanager.__recreate__()
                    # item.config.__reinit__(new_pm)
                    # TerminalReporter

                    return self.pytest_runtest_protocol(item=item, nextitem=None)

                hook = item.ihook
                setup = hook.pytest_runtest_setup
                make_report = hook.pytest_runtest_makereport

                from cloudpickle import loads, dumps
                raw = dumps(item, 4)
                item3 = loads(raw)

                # item2 = deserialize(*serialize(item))
                # fut = self.client.submit(run_test, item)
                fut = run_test(item)
                yield fut

        # TODO: use something like as_completed for these results.
        results = compute(list(generate_tasks()))
        # log these reports to the console.
        for r in results:
            for t in r:
                for report in t:
                    session.ihook.pytest_runtest_logreport(report=report)

        return True

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


def pytest_addoption(parser):
    group = parser.getgroup('dask')
    group.addoption(
        '--dask',
        action='store_true',
        dest='dask',
        default=False,
        help='Set the value for the fixture "dask".'
    )


@pytest.mark.trylast
def pytest_configure(config):
    if config.getoption("dask"):
        dask_session = DaskRunner(config)
        config.pluginmanager.register(dask_session, "dask_session")
