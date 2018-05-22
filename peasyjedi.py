import os
import sys
import ctypes
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Geany
from gi.repository import GeanyScintilla
from gi.repository import Peasy

try:
    import jedi
    jedi.settings.case_insensitive_completion = False
    HAS_JEDI = True
except ImportError:
    print("jedi not found, python auto-completion not possible.")
    HAS_JEDI = False

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
        self.jedi_config = os.path.join(
            self.geany_plugin.geany_data.app.configdir, "plugins/pyjedi.conf")
        o = self.geany_plugin.geany_data.object
        self.phandler = o.connect("project-open", self.on_project_open)
        self.handler = o.connect("editor-notify", self.on_editor_notify)
        #  o.connect("project-close", self.on_project_close)
        # load startup config
        self.keyfile = GLib.KeyFile.new()
        if (os.path.isfile(self.jedi_config)):
            self.keyfile.load_from_file(self.jedi_config,
                                        GLib.KeyFileFlags.KEEP_COMMENTS)
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
        if not Geany.highlighting_is_code_style(sci.get_lexer(),
                                                sci.get_style_at(pos - 2)):
            return False
        if nt.nmhdr.code in (GeanyScintilla.SCN_CHARADDED,
                             GeanyScintilla.SCN_AUTOCSELECTION):
            self.complete_python(editor, nt.ch, getattr(nt, 'text', None))

    def complete_python(self, editor, char, text=None):
        char = chr(char)
        if char in ('\r', '\n', '>', '/', '(', ')', '{', '[', '"', '\'', '}',
                    ':'):
            return
        sci = editor.sci
        pos = sci.get_current_position()
        col = sci.get_col_from_position(pos)
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
        word_at_pos = editor.get_word_at_pos(pos, GEANY_WORDCHARS + ".")
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

        fp = editor.document.real_path or editor.document.file_name
        faked_gir_path = os.path.join(
            os.path.expanduser('~'), '.cache/fakegir')
        if os.path.isdir(faked_gir_path):
            path = [faked_gir_path] + self.sys_path
        else:
            print('Support for GIR may be missing')
            path = self.sys_path
        try:
            script = jedi.Script(
                buffer, line=None, column=None, path=fp, sys_path=path)
        except ValueError as e:
            print(e)
            return
        if not script:
            return
        data = ""
        doc = None
        for count, complete in enumerate(script.completions()):
            name = complete.name
            if name.startswith('__') and name.endswith('__'):
                continue
            if hasattr(Geany, 'msgwin_msg_add_string') and text is not None:
                if text != name:
                    continue
                #  # we have to use custom names here because .type and .params can't
                #  # be overridden (they are properties)
                doc = complete.docstring()
                break
            if count > 0:
                data += "\n"
            data += name
            try:
                complete.params
            except AttributeError:
                data += "?2"
            else:
                data += "?1"
            #  data += name+("?2" if complete.name_with_symbols else "?1")
            if count == 49:
                break
        Geany.msgwin_clear_tab(Geany.MessageWindowTabNum.MESSAGE)
        if doc:
            Geany.msgwin_msg_add_string(Geany.MsgColors.BLACK, line - 1,
                                        editor.document, "Doc:\n" + doc)
            Geany.msgwin_switch_tab(Geany.MessageWindowTabNum.MESSAGE, False)
        elif data:
            self.scintilla_command(
                sci,
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
                self.keyfile.load_from_file(self.jedi_config,
                                            GLib.KeyFileFlags.KEEP_COMMENTS)
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
