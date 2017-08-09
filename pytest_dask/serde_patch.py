"""Utility module to ensure that pytest classes are mostly serializable.  This is required to be able to use
dask-distributed.

"""

from __future__ import absolute_import, print_function

from io import BytesIO
from weakref import WeakKeyDictionary

from _pytest.assertion.rewrite import AssertionRewritingHook
from _pytest.capture import EncodedFile, SysCapture, patchsysdict, CaptureManager
from _pytest.compat import CaptureIO
from _pytest.config import Config, PytestPluginManager
from _pytest.config import get_plugin_manager
from _pytest.pytester import HookRecorder, Testdir
from _pytest.terminal import TerminalReporter
from _pytest.vendored_packages.pluggy import PluginManager

from cloudpickle import CloudPickler
from py._apipkg import ApiModule
from pygments.lexers import _automodule
from six import MovedModule

CloudPickler.dispatch[ApiModule] = CloudPickler.save_module
CloudPickler.dispatch[MovedModule] = CloudPickler.save_module
# CloudPickler.dispatch[]


def apply_getnewargs(cls, ref):
    cls.__getnewargs__ = ref.__getnewargs__
    cls.__getstate__ = ref.__getstate__


def apply_getsetstate(cls, ref):
    cls.__getstate__ = ref.__getstate__
    cls.__setstate__ = ref.__setstate__


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

        return {}

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
