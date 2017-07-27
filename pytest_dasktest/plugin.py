# -*- coding: utf-8 -*-
from io import BytesIO
from weakref import WeakKeyDictionary

import pytest
from _pytest.assertion.rewrite import AssertionRewritingHook
from _pytest.capture import EncodedFile, SysCapture, patchsysdict, CaptureManager
from _pytest.compat import CaptureIO
from _pytest.config import Config, PytestPluginManager
from _pytest.config import get_plugin_manager
from _pytest.pytester import HookRecorder, Testdir
from _pytest.runner import CallInfo
from _pytest.terminal import TerminalReporter
from _pytest.vendored_packages.pluggy import PluginManager
from cloudpickle import CloudPickler
from dask import compute, delayed
from distributed import Client, LocalCluster
from py._apipkg import ApiModule
from pygments.lexers import _automodule
from six import MovedModule

CloudPickler.dispatch[ApiModule] = CloudPickler.save_module
CloudPickler.dispatch[MovedModule] = CloudPickler.save_module


def apply_getsetstate(cls, ref):
    cls.__getstate__ = ref.__getstate__
    cls.__setstate__ = ref.__setstate__


def apply_getnewargs(cls, ref):
    cls.__getnewargs__ = ref.__getnewargs__
    cls.__getstate__ = ref.__getstate__


class _DictState:
    def __getstate__(self):
        state = self.__dict__
        return state

    def __setstate__(self, state):
        for k, v in state.items():
            setattr(self, k, v)


apply_getsetstate(_automodule, _DictState)
apply_getsetstate(Config, _DictState)


def reinit(self, pluginmanager):
    self.pluginmanager = pluginmanager
    self.trace = self.pluginmanager.trace.root.get("config")
    self.hook = self.pluginmanager.hook
    self._warn = self.pluginmanager._warn


Config.__reinit__ = reinit


def getpystate(self):
    # don't take anything -- we should be able to reimport it.
    state = {}
    return state


def setpystate(self, state):
    import py
    for k, v in py.__dict__.items():
        setattr(self, k, v)


ApiModule.__getstate__ = getpystate
ApiModule.__setstate__ = setpystate


class _:
    def __getstate__(self):
        state = dict(name=self.name, mod=self.mod)
        return state

    __setstate__ = _DictState.__setstate__
    MovedModule.__reduce_ex__ = object.__reduce_ex__


apply_getsetstate(MovedModule, _)


# def get_state(self):
#     d = self.__dict__
#     exclude_keys = set()
#     if isinstance(self._file, FileIO) and self._file.name == '<stdout>':
#         exclude_keys = {'_file'}
#
#     state = {k: v for k, v in self.__dict__.items() if k not in exclude_keys}
#     return state
#
#
# def set_state(self, state):
#     for k, v in state.items():
#         setattr(self, k, v)
#     if '_file' not in state:
#         setattr(self, '_file', sys.stdout)
#
#
# TerminalWriter.__getstate__ = get_state
# TerminalWriter.__setstate__ = set_state

class _CaptureIOGetstate:
    def __getstate__(self):
        assert isinstance(self, CaptureIO)
        return {'value': self.getvalue()}

    def __setstate__(self, state):
        assert isinstance(self, CaptureIO)
        self.write(state['value'])


apply_getsetstate(CaptureIO, _CaptureIOGetstate)


class _SysCaptureGetstate:
    def __getstate__(self):
        reverse_name = {v: k for k, v in patchsysdict.items()}
        return dict(fd=reverse_name[self.name])

    def __setstate__(self, state):
        self.__init__(state['fd'])


apply_getsetstate(SysCapture, _SysCaptureGetstate)


class _:
    def __getnewargs__(self):
        return (self.request, self.request.config._tmpdirhandler)

    def __getstate__(self):
        def promote_weak_dict(wd):
            assert isinstance(wd, WeakKeyDictionary)
            return dict(wd.items())

        def handle_value(v):
            if isinstance(v, WeakKeyDictionary):
                return promote_weak_dict(v)
            else:
                return v

        return {}  # k: handle_value(v) for k, v in self.__dict__.items() if k not in {'_savesyspath', '_mod_collections'}}

    # def __getstate__(self):
    #     return {}

    # def __setstate__(self, state):
    Testdir.__getnewargs__ = __getnewargs__
    Testdir.__getstate__ = __getstate__


class _EncodedFileSerde:
    def __getstate__(self):
        assert isinstance(self, EncodedFile)
        current_position = self.buffer.seek(0, 1)
        self.buffer.seek(0)
        value = self.buffer.read()
        self.buffer.seek(current_position, 0)
        return {'value': value, 'encoding': self.encoding}

    def __setstate__(self, state):
        assert isinstance(self, EncodedFile)
        setattr(self, 'encoding', state['encoding'])
        buffer = BytesIO(state['value'])
        setattr(self, 'buffer', buffer)


apply_getsetstate(EncodedFile, _EncodedFileSerde)


class _ConfigState:
    def __getstate__(self):
        return {'config': self.config}

    def __setstate__(self, state):
        self.config = state['config']

    def __reinit__(self, pluginmanager):
        # sleep a bit and then init?
        self.__init__(self.config)


apply_getsetstate(TerminalReporter, _ConfigState)
TerminalReporter.__reinit__ = _ConfigState.__reinit__
apply_getsetstate(AssertionRewritingHook, _ConfigState)
AssertionRewritingHook.__reinit__ = _ConfigState.__reinit__


class _:
    def __getstate__(self):
        return {'_method': self._method}

    def __setstate__(self, state):
        self._method = state['_method']
        self.init_capturings()

    CaptureManager.__getstate__ = __getstate__
    CaptureManager.__setstate__ = __setstate__


class _:
    def __getnewargs__(self):
        assert isinstance(self, PluginManager)
        return self.project_name, self._implprefix

    def __getstate__(self):
        state = {'_1_plugins': self.get_plugins(), '_1_project_name': self.project_name,
                 '_1_implprefix': self._implprefix}
        return state

    def __setstate__(self, state):
        for k, v in state.items():
            setattr(self, k, v)

    def __recreate__(self):
        new_pm = PytestPluginManager()
        for plugin in self._1_plugins:
            ret = new_pm.register(plugin)
            if hasattr(plugin, '__reinit__'):
                plugin.__reinit__(new_pm)
        return new_pm

    PytestPluginManager.__getnewargs__ = __getnewargs__
    PytestPluginManager.__getstate__ = __getstate__
    PytestPluginManager.__setstate__ = __setstate__
    PytestPluginManager.__recreate__ = __recreate__


HookRecorder.__getstate__ = lambda self: {}
def setstate(self, state):
    setattr(self, '_pluginmanager', get_plugin_manager())
HookRecorder.__setstate__ = setstate



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
