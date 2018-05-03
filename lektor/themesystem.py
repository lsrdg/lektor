import os
import sys
from weakref import ref as weakref
from inifile import IniFile
import pkg_resources

from lektor._compat import iteritems, itervalues
from lektor.context import get_ctx


def get_theme(theme_id_or_class, env=None):
    """Looks up the theme instance by id or class."""
    if env is None:
        ctx = get_ctx()
        if ctx is None:
            raise RuntimeError('Context is unavailable and no environment '
                               'was passed to the function.')
        env = ctx.env
    theme_id = env.theme_ids_by_class.get(theme_id_or_class,
                                            theme_id_or_class)
    try:
        return env.themes[theme_id]
    except KeyError:
        raise LookupError('Theme %r not found' % theme_id)


class Theme(object):
    """This needs to be subclassed for custom themes."""
    name = 'Your Theme Name'
    description = 'Description goes here'

    def __init__(self, env, id):
        self._env = weakref(env)
        self.id = id

    @property
    def env(self):
        rv = self._env()
        if rv is None:
            raise RuntimeError('Environment went away')
        return rv

    @property
    def version(self):
        from pkg_resources import get_distribution
        return get_distribution('lektor-' + self.id).version

    @property
    def path(self):
        mod = sys.modules[self.__class__.__module__.split('.')[0]]
        path = os.path.abspath(os.path.dirname(mod.__file__))
        if not path.startswith(self.env.project.get_package_cache_path()):
            return path
        return None

    @property
    def import_name(self):
        return self.__class__.__module__ + ':' + self.__class__.__name__

    def get_lektor_config(self):
        """Returns the global config."""
        ctx = get_ctx()
        if ctx is not None:
            cfg = ctx.pad.db.config
        else:
            cfg = self.env.load_config()
        return cfg

    @property
    def config_filename(self):
        """The filename of the theme specific config file."""
        return os.path.join(self.env.root_path, 'configs', self.id + '.ini')

    def get_config(self, fresh=False):
        """Returns the config specific for this theme.  By default this
        will be cached for the current build context but this can be
        disabled by passing ``fresh=True``.
        """
        ctx = get_ctx()
        if ctx is not None and not fresh:
            cache = ctx.cache.setdefault(__name__ + ':configs', {})
            cfg = cache.get(self.id)
            if cfg is None:
                cfg = IniFile(self.config_filename)
                cache[self.id] = cfg
        else:
            cfg = IniFile(self.config_filename)
        if ctx is not None:
            ctx.record_dependency(self.config_filename)
        return cfg

    def emit(self, event, **kwargs):
        return self.env.themesystem.emit(self.id + '-' + event, **kwargs)

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'path': self.path,
            'import_name': self.import_name,
        }


def load_themes():
    """Loads all available themes and returns them."""
    rv = {}
    for ep in pkg_resources.iter_entry_points('lektor.themes'):
        match_name = 'lektor-' + ep.name.lower()
        if match_name != ep.dist.project_name.lower():
            raise RuntimeError('Mismatching entry point name.  Found '
                               '"%s" but expected "%s" for package "%s".'
                               % (ep.name, ep.dist.project_name[7:],
                                  ep.dist.project_name))
        rv[ep.name] = ep.load()
    return rv


def initialize_themes(env):
    """Initializes the themes for the environment."""
    themes = load_themes()
    for theme_id, theme_cls in iteritems(themes):
        env.theme_controller.instanciate_theme(theme_id, theme_cls)
    env.theme_controller.emit('setup-env')


class ThemeController(object):
    """Helper management class that is used to control themes through
    the environment.
    """

    def __init__(self, env):
        self._env = weakref(env)

    @property
    def env(self):
        rv = self._env()
        if rv is None:
            raise RuntimeError('Environment went away')
        return rv

    def instanciate_theme(self, theme_id, theme_cls):
        env = self.env
        if theme_id in env.themes:
            raise RuntimeError('Theme "%s" is already registered'
                               % theme_id)
        env.themes[theme_id] = theme_cls(env, theme_id)
        env.theme_ids_by_class[theme_cls] = theme_id

    def iter_themes(self):
        # XXX: sort?
        return itervalues(self.env.themes)

    def emit(self, event, **kwargs):
        rv = {}
        funcname = 'on_' + event.replace('-', '_')
        for theme in self.iter_themes():
            handler = getattr(theme, funcname, None)
            if handler is not None:
                rv[theme.id] = handler(**kwargs)
        return rv
