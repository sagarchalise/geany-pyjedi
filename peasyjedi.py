import os
import sys
import ctypes
""" Taken from gnome-builder jedi plugin for gi related imports."""
import gi
# lxml is faster than the Python standard library xml, and can ignore invalid
# characters (which occur in some .gir files).
# gnome-code-assistance also needs lxml, so I think it's okay to use it here.
try:
    import lxml.etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False
    print('Warning: python3-lxml is not installed, no documentation will be available in Python auto-completion')
import os.path
import sqlite3
import threading

gi.require_version('GIRepository', '2.0')
gi.require_version('Gtk', '3.0')

from collections import OrderedDict

from gi.importer import DynamicImporter
from gi.module import IntrospectionModule
from gi.module import FunctionInfo

from gi.repository import GIRepository
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Geany
from gi.repository import GeanyScintilla
from gi.repository import Peasy
from gi.types import GObjectMeta
from gi.types import StructMeta

gi_importer = DynamicImporter('gi.repository')

_TYPE_KEYWORD = 1
_TYPE_FUNCTION = 2
_TYPE_CLASS = 3
_TYPE_INSTANCE = 4
_TYPE_PARAM = 5
_TYPE_IMPORT = 6
_TYPE_MODULE = 7

_TYPES = {
    'class': _TYPE_CLASS,
    'function': _TYPE_FUNCTION,
    'import': _TYPE_IMPORT,
    'instance': _TYPE_INSTANCE,
    'keyword': _TYPE_KEYWORD,
    'module':  _TYPE_MODULE,
    'param': _TYPE_PARAM,
}

_ICONS = {
    _TYPE_KEYWORD: 'lang-class-symbolic',
    _TYPE_FUNCTION: 'lang-function-symbolic',
    _TYPE_CLASS: 'lang-class-symbolic',
    _TYPE_INSTANCE: 'lang-variable-symbolic',
    _TYPE_PARAM: 'lang-variable-symbolic',
    _TYPE_IMPORT: 'lang-namespace-symbolic',
    _TYPE_MODULE: 'lang-namespace-symbolic',
}

try:
    import jedi
    from jedi.evaluate.compiled import CompiledObject
    from jedi.evaluate.compiled import get_special_object
    from jedi.evaluate.compiled import _create_from_name
    from jedi.evaluate.base_context import Context, ContextSet
    from jedi.evaluate.docstrings import _evaluate_for_statement_string
    from jedi.evaluate.imports import Importer

    class PatchedJediCompiledObject(CompiledObject):
        "A modified version of Jedi CompiledObject to work with GObject Introspection modules"

        def __init__(self, evaluator, obj, parent_context=None, faked_class=None):
            # we have to override __init__ to change super(CompiledObject, self)
            # to Context, in order to prevent an infinite recursion
            Context.__init__(self, evaluator, parent_context)
            self.obj = obj
            self.tree_node = faked_class

        def _cls(self):
            if self.obj.__class__ == IntrospectionModule:
                return self
            else:
                return super()._cls(self)

        @property
        def py__call__(self):
            def actual(params):
                # Parse the docstring to find the return type:
                ret_type = ''
                if '->' in self.obj.__doc__:
                    ret_type = self.obj.__doc__.split('->')[1].strip()
                    ret_type = ret_type.replace(' or None', '')
                if ret_type.startswith('iter:'):
                    ret_type = ret_type[len('iter:'):]  # we don't care if it's an iterator

                if hasattr(__builtins__, ret_type):
                    # The function we're inspecting returns a builtin python type, that's easy
                    # (see test/test_evaluate/test_compiled.py in the jedi source code for usage)
                    builtins = get_special_object(self.evaluator, 'BUILTINS')
                    builtin_obj = builtins.py__getattribute__(ret_type)
                    obj = _create_from_name(self.evaluator, builtins, builtin_obj, "")
                    return self.evaluator.execute(obj, params)
                else:
                    # The function we're inspecting returns a GObject type
                    parent = self.parent_context.obj.__name__
                    if parent.startswith('gi.repository'):
                        parent = parent[len('gi.repository.'):]
                    else:
                        # a module with overrides, such as Gtk, behaves differently
                        parent_module = self.parent_context.obj.__module__
                        if parent_module.startswith('gi.overrides'):
                            parent_module = parent_module[len('gi.overrides.'):]
                            parent = '%s.%s' % (parent_module, parent)

                    if ret_type.startswith(parent):
                        # A pygobject type in the same module
                        ret_type = ret_type[len(parent):]
                    else:
                        # A pygobject type in a different module
                        return_type_parent = ret_type.split('.', 1)[0]
                        ret_type = 'from gi.repository import %s\n%s' % (return_type_parent, ret_type)
                    result = _evaluate_for_statement_string(self.parent_context, ret_type)
                    return set(result)
            if type(self.obj) == FunctionInfo:
                return actual
            return super().py__call__

    # we need to override CompiledBoundMethod without changing it much,
    # just so it'll not get confused due to our overriden CompiledObject
    class PatchedCompiledBoundMethod(PatchedJediCompiledObject):
        def __init__(self, func):
            super().__init__(func.evaluator, func.obj, func.parent_context, func.tree_node)

    class PatchedJediImporter(Importer):
        "A modified version of Jedi Importer to work with GObject Introspection modules"
        def follow(self):
            module_list = super().follow()
            import_path = '.'.join((i if isinstance(i, str) else i.value for i in self.import_path))
            if import_path.startswith('gi.repository'):
                try:
                    module = gi_importer.load_module(import_path)
                    module_list = ContextSet(PatchedJediCompiledObject(self._evaluator, module))
                except ImportError:
                    pass
            return module_list
    original_jedi_get_module = jedi.evaluate.compiled.fake.get_module

    def patched_jedi_get_module(obj):
        "Work around a weird bug in jedi"
        try:
            return original_jedi_get_module(obj)
        except ImportError as e:
            if e.msg == "No module named 'gi._gobject._gobject'":
                return original_jedi_get_module('gi._gobject')

    jedi.evaluate.compiled.fake.get_module = patched_jedi_get_module
    jedi.evaluate.compiled.CompiledObject = PatchedJediCompiledObject
    jedi.evaluate.context.instance.CompiledBoundMethod = PatchedCompiledBoundMethod
    jedi.evaluate.imports.Importer = PatchedJediImporter
    jedi.settings.case_insensitive_completion = False
    HAS_JEDI = True
except ImportError:
    print("jedi not found, python auto-completion not possible.")
    HAS_JEDI = False

GIR_PATH_LIST = []

def init_gir_path_list():
    global GIR_PATH_LIST
    paths = OrderedDict()

    # Use GI_TYPELIB_PATH and the search path used by gobject-introspection
    # to guess the correct path of gir files. It is likely that gir files and
    # typelib files are installed in the same prefix.
    search_path = GIRepository.Repository.get_default().get_search_path()
    if 'GI_TYPELIB_PATH' in os.environ:
        search_path = os.environ['GI_TYPELIB_PATH'].split(':') + search_path

    for typelib_path in search_path:
        # Check whether the path is end with lib*/girepository-1.0. If
        # not, it is likely to be a custom path used for testing that
        # we should not use.
        typelib_path = os.path.normpath(typelib_path)
        typelib_basename = os.path.basename(typelib_path)
        if typelib_basename != 'girepository-1.0':
            continue

        path_has_lib = False
        gir_path, gir_basename = typelib_path, typelib_basename
        while gir_basename != '':
            gir_path = os.path.normpath(os.path.join(gir_path, os.path.pardir))
            gir_basename = os.path.basename(gir_path)
            if gir_basename.startswith('lib'):
                path_has_lib = True
                break

        if not path_has_lib:
            continue
        # Replace lib component with share.
        gir_path = os.path.normpath(os.path.join(gir_path, os.path.pardir,
            'share', os.path.relpath(typelib_path, gir_path)))
        # Replace girepository-1.0 component with gir-1.0.
        gir_path = os.path.normpath(os.path.join(gir_path, os.path.pardir,
            'gir-1.0'))
        paths[gir_path] = None

    # It is also possible for XDG_DATA_DIRS to contain a list of prefixes.
    if 'XDG_DATA_DIRS' in os.environ:
        for xdg_data_path in os.environ['XDG_DATA_DIRS'].split(':'):
            gir_path = os.path.normpath(os.path.join(
                xdg_data_path, 'gir-1.0'))
            paths[gir_path] = None

    # Ignore non-existent directories to prevent exceptions.
    GIR_PATH_LIST = list(filter(os.path.isdir, paths.keys()))

init_gir_path_list()

class DocumentationDB(object):
    def __init__(self):
        self.db = None
        self.cursor = None

    def close(self):
        "Close the DB if open"
        if self.db is not None:
            self.cursor.close()
            self.db.close()
            self.cursor = None
            self.db = None

    def open(self):
        "Open the DB (if needed)"
        if self.db is None:
            doc_db_path = os.path.join(GLib.get_user_cache_dir(), 'gnome-builder', 'jedi', 'girdoc.db')
            try:
                os.makedirs(os.path.dirname(doc_db_path))
            except:
                pass
            self.db = sqlite3.connect(doc_db_path)
            self.cursor = self.db.cursor()
            # Create the tables if they don't exist to prevent exceptions later on
            self.cursor.execute('CREATE TABLE IF NOT EXISTS doc (symbol text, library_version text, doc text, gir_file text)')
            self.cursor.execute('CREATE TABLE IF NOT EXISTS girfiles (file text, last_modified integer)')

    def query(self, symbol, version):
        "Query the documentation DB"
        self.open()
        self.cursor.execute('SELECT doc FROM doc WHERE symbol=? AND library_version=?', (symbol, version))
        result = self.cursor.fetchone()
        if result is not None:
            return result[0]
        else:
            return None

    def update(self, close_when_done=False):
        "Build the documentation DB and ensure it's up to date"
        if not HAS_LXML:
            return  # Can't process the gir files without lxml
        ns = {'core': 'http://www.gtk.org/introspection/core/1.0',
              'c': 'http://www.gtk.org/introspection/c/1.0'}
        self.open()
        cursor = self.cursor
        processed_gir_files = {}

        # I would use scandir for better performance, but it requires newer Python
        for gir_path in GIR_PATH_LIST:
            for gir_file in os.listdir(gir_path):
                if not gir_file.endswith('.gir'):
                    continue
                if gir_file in processed_gir_files:
                    continue
                processed_gir_files[gir_file] = None
                filename = os.path.join(gir_path, gir_file)
                mtime = os.stat(filename).st_mtime
                cursor.execute('SELECT * from girfiles WHERE file=?', (filename,))
                result = cursor.fetchone()
                if result is None:
                    cursor.execute('INSERT INTO girfiles VALUES (?, ?)', (filename, mtime))
                else:
                    if result[1] >= mtime:
                        continue
                    else:
                        # updated
                        cursor.execute('DELETE FROM doc WHERE gir_file=?', (filename,))
                        cursor.execute('UPDATE girfiles SET last_modified=? WHERE file=?', (mtime, filename))
                parser = lxml.etree.XMLParser(recover=True)
                tree = lxml.etree.parse(filename, parser=parser)
                try:
                    namespace = tree.find('core:namespace', namespaces=ns)
                except:
                    print("Failed to parse", filename)
                    continue
                library_version = namespace.attrib['version']
                for node in namespace.findall('core:class', namespaces=ns):
                    doc = node.find('core:doc', namespaces=ns)
                    if doc is not None:
                        symbol = node.attrib['{http://www.gtk.org/introspection/glib/1.0}type-name']
                        cursor.execute("INSERT INTO doc VALUES (?, ?, ?, ?)",
                                       (symbol, library_version, doc.text, filename))
                for method in namespace.findall('core:method', namespaces=ns) + \
                              namespace.findall('core:constructor', namespaces=ns) + \
                              namespace.findall('core:function', namespaces=ns):
                    doc = method.find('core:doc', namespaces=ns)
                    if doc is not None:
                        symbol = method.attrib['{http://www.gtk.org/introspection/c/1.0}identifier']
                        cursor.execute("INSERT INTO doc VALUES (?, ?, ?, ?)",
                                       (symbol, library_version, doc.text, filename))
        self.db.commit()
        if close_when_done:
            self.close()


def update_doc_db_on_startup():
    db = DocumentationDB()
    threading.Thread(target=db.update, args={'close_when_done': True}).start()

update_doc_db_on_startup()


_ = Peasy.gettext

GEANY_WORDCHARS = "_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

class JediPlugin(Peasy.Plugin, Peasy.PluginConfigure):
    __gtype_name__ = "PeasyJedi"
    
    def __init__(self):
        self.sys_path = sys.path
        self.phandler = None
        self.handler = None
        self.jedi_config = None
        self.default_include = None
        self.completion_words = None

    def do_enable(self):
        self.jedi_config = os.path.join(self.geany_plugin.geany_data.app.configdir, "plugins/pyjedi.conf")
        o = self.geany_plugin.geany_data.object
        self.phandler = o.connect("project-open", self.on_project_open)
        self.handler = o.connect("editor-notify", self.on_editor_notify)
        #  o.connect("project-close", self.on_project_close)
        # load startup config
        self.keyfile = GLib.KeyFile.new()        
        if (os.path.isfile(self.jedi_config)):
            self.keyfile.load_from_file(self.jedi_config, GLib.KeyFileFlags.KEEP_COMMENTS)
            self.default_include = self.keyfile.get_string("pyjedi", "path")
            self.append_sys_path(self.default_include)
        return True
        
    def do_disable(self):
        o = self.geany_plugin.geany_data.object
        o.disconnect(self.phandler)
        o.disconnect(self.handler)

    def append_sys_path(self, path):
        if path and path not in self.sys_path:
            self.sys_path.append(path)

    @staticmethod
    def scintilla_command(sci, sci_msg, sci_cmd, lparam, data):
        sci.send_command(sci_cmd)
        if data:
            data = ctypes.c_char_p(data.encode('utf8'))
            tt = ctypes.cast(data, ctypes.c_void_p).value
            sci.send_message(sci_msg, lparam, tt)
    #  def on_project_close(self, g_obj):
        #  print(dir(g_obj))
        #  print(self.geany_plugin.geany_data.app.project)
        
    def on_project_open(self, g_obj, cnf_file):
        proj = self.geany_plugin.geany_data.app.project
        if proj:
            self.append_sys_path(proj.base_path)

    def on_editor_notify(self, g_obj, editor, nt):
        cur_doc = editor.document or Geany.Document.get_current()
        if not cur_doc:
            return False
        if cur_doc.file_type.id != Geany.FiletypeID.FILETYPES_PYTHON:
            return False
        if not HAS_JEDI:
            return False
        sci = editor.sci
        pos = sci.get_current_position()
        if pos < 2:
            return False
        if not Geany.highlighting_is_code_style(sci.get_lexer(), sci.get_style_at(pos-2)):
            return False
        if nt.nmhdr.code in (GeanyScintilla.SCN_CHARADDED, GeanyScintilla.SCN_AUTOCSELECTION):
            self.complete_python(editor, nt.ch, getattr(nt, 'text', None))

    def complete_python(self, editor, char, text=None):
        char = chr(char)
        if char in ('\r', '\n', '>', '/', '(', ')', '{', '[', '"', '\'', '}', ':'):
            return
        sci = editor.sci
        pos = sci.get_current_position()
        col = sci.get_col_from_position(pos);
        if col == 1 and char in ('f', 'i'):
            return
        line = sci.get_current_line()
        word_at_pos = sci.get_line(line)
        if not word_at_pos:
            return
        if word_at_pos.lstrip().startswith(('fr', 'im')):
            buffer = word_at_pos.rstrip()
            import_check = True
        else:
            buffer = sci.get_contents_range(0, pos).rstrip()
            import_check = False
        word_at_pos = editor.get_word_at_pos(pos, GEANY_WORDCHARS+".")
        if not word_at_pos:
            return
        rootlen = len(word_at_pos)
        if '.' in word_at_pos:
            word_at_pos = editor.get_word_at_pos(pos, GEANY_WORDCHARS)
            if not word_at_pos:
                rootlen = 0
            else:
                rootlen = len(word_at_pos)
        elif not rootlen or (rootlen < 2 and not import_check):
            return

        def get_gi_obj(info):
            """ Get a GObject Introspection object from a jedi Completion, or None if the completion is not GObject Introspection related """
            if (type(info._module) == PatchedJediCompiledObject and
               info._module.obj.__class__ == IntrospectionModule):
                return next(info._name.infer()).obj
            else:
                return None
        fp = editor.document.real_path or editor.document.file_name
        try:
            script = jedi.Script(buffer, line=None, column=None, path=fp, sys_path=self.sys_path)
        except ValueError as e:
            print(e)
            return
        if not script:
            return
        data = ""
        doc = None
        db = DocumentationDB()
        for count, complete in enumerate(script.completions()):
            name = complete.name
            if name.startswith('__') and name.endswith('__'):
                continue
            print(text)
            if hasattr(Geany, 'msgwin_msg_add_string') and text is not None:
                if text != name:
                    continue
                #  # we have to use custom names here because .type and .params can't
                #  # be overridden (they are properties)
                doc = complete.docstring()
                obj = get_gi_obj(complete)

                if obj is not None:
                    # get documentation for this GObject Introspection object
                    symbol = None

                    if type(obj) == GObjectMeta or type(obj) == StructMeta:
                        if hasattr(obj, '__info__'):
                            symbol = obj.__info__.get_type_name()
                    elif type(obj) == FunctionInfo:
                        symbol = obj.get_symbol()

                    if symbol is not None:
                        result = db.query(symbol, complete._module.obj._version)
                        if result is not None:
                            doc = result
                break
            if count > 0:
                data += "\n"
            data += name
            if count == 49:
                break
        db.close()
        Geany.msgwin_clear_tab(Geany.MessageWindowTabNum.MESSAGE)
        if doc:
            Geany.msgwin_msg_add_string(Geany.MsgColors.BLACK, line-1, editor.document, "Doc:\n"+doc)
            Geany.msgwin_switch_tab(Geany.MessageWindowTabNum.MESSAGE, False);
        elif data:
            self.scintilla_command(sci,
                sci_cmd=GeanyScintilla.SCI_AUTOCCANCEL,
                sci_msg=GeanyScintilla.SCI_AUTOCSHOW,
                lparam=rootlen,
                data=data)

    def on_configure_response(self, dlg, response_id, user_data):
        if (response_id in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK)):
            inc = user_data.get_text()
            if self.default_include is not None and inc == self.default_include:
                return
            if (os.path.isfile(self.jedi_config)):
                self.keyfile.load_from_file(self.jedi_config, GLib.KeyFileFlags.KEEP_COMMENTS)
                self.keyfile.set_string("pyjedi", "path", inc or '')
                self.keyfile.save_to_file(self.jedi_config)
            if self.default_include in self.sys_path:
                self.sys_path.remove(self.default_include) 
            self.append_sys_path(inc)
            self.default_include = inc

    def do_configure(self, dialog):
        #  frame = Gtk.Frame()
        align = Gtk.Alignment.new(0, 0, 1, 0)
        align.props.left_padding = 12
        vbox = Gtk.VBox(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_border_width(2)
        label = Gtk.Label(_("Extra Path to Include with jedi:"))
        label.set_alignment(0, 0.5)
        entry = Gtk.Entry()
        if self.default_include:
            entry.set_text(self.default_include)
        vbox.add(label)
        vbox.add(entry)
        align.add(vbox)
        dialog.connect("response", self.on_configure_response, entry)
        return align
