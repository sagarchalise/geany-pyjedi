import os
import sys
import ctypes
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Geany
from gi.repository import GeanyScintilla
from gi.repository import Peasy

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
        sci = editor.sci
        pos = sci.get_current_position()
        if pos < 2:
            return False
        if not Geany.highlighting_is_code_style(sci.get_lexer(), sci.get_style_at(pos-2)):
            return False
        try:
            import jedi
        except ImportError:
            print('No jedi installed.')
            return False
        if nt.nmhdr.code == GeanyScintilla.SCN_CHARADDED: 
        #  (GeanyScintilla.SCN_CHARADDED, GeanyScintilla.SCN_AUTOCSELECTION):
            self.complete_python(editor, nt.ch, getattr(nt, 'text', None))

    def complete_python(self, editor, char, text=None):
        if char in ('\r', '\n', '>', '/', '(', ')', '{', '[', '"', '\'', '}', ':'):
            return
        sci = editor.sci
        pos = sci.get_current_position()
        line = sci.get_current_line()+1
        word_at_pos = sci.get_line(line-1)
        if word_at_pos.startswith(('from', 'import')):
            line = 1
            buffer = word_at_pos
            import_check = True
        else:
            buffer = sci.get_contents_range(0, pos)
            import_check = False
        word_at_pos = editor.get_word_at_pos(pos, GEANY_WORDCHARS+".")
        if not word_at_pos:
            return
        col = sci.get_col_from_position(pos);
        rootlen = len(word_at_pos)
        if '.' in word_at_pos:
            word_at_pos = editor.get_word_at_pos(pos, GEANY_WORDCHARS)
            if not word_at_pos:
                rootlen = 0
            else:
                rootlen = len(word_at_pos)
        elif not rootlen or (rootlen < 2 and not import_check):
            return
        import jedi
        jedi.settings.case_insensitive_completion = False
        script = jedi.Script(buffer, line, col, sys_path=self.sys_path)
        if not script:
            return
        completions = script.completions()
        if not completions:
            return
        word = ""
        for complete in completions:
            name = complete.name
            if name.startswith('__'):
                continue
            word += "{}\n".format(name)
        word = ctypes.c_char_p(word.encode('utf8'))
        tt = ctypes.cast(word, ctypes.c_void_p).value
        sci.send_command(GeanyScintilla.SCI_AUTOCCANCEL)
        sci.send_message(GeanyScintilla.SCI_AUTOCSHOW, rootlen, tt)

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
        vbox = Gtk.VBox(spacing=2)
        vbox.set_border_width(2)
        label = Gtk.Label(_("Extra Path to Include with jedi:"))
        #  label.set_alignment(0, 0.5)
        entry = Gtk.Entry()
        if self.default_include:
            entry.set_text(self.default_include)
        vbox.add(label)
        vbox.add(entry)
        dialog.connect("response", self.on_configure_response, entry)
        return vbox
