import ctypes
import os
from configparser import SafeConfigParser
from gettext import gettext as _
from gi.repository import Gtk, GObject
from gi.repository import Geany
from gi.repository import GeanyScintilla
from gi.repository import Peasy

GEANY_WORDCHARS = "_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

class JediPlugin(Peasy.Plugin):
    __gtype_name__ = "PeasyJedi"
    
    def do_enable(self):
        o = self.geany_plugin.geany_data.object
        #  o.connect("project-open", self.on_project_open)
        o.connect("editor-notify", self.on_editor_notify)
    

    def do_disable(self):
        pass

    def load_config(self):
        self.cfg_path = os.path.join(self.geany_plugin.geany_data.app.configdir, "plugins", "pyemmet.conf")
        self.cfg = SafeConfigParser()
        self.cfg.read(self.cfg_path)

    def save_config(self):
        GObject.idle_add(self.on_save_config_timeout)

    def on_save_config_timeout(self, data=None):
        self.cfg.write(open(self.cfg_path, 'w'))
        return False

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
        if nt.nmhdr.code in (GeanyScintilla.SCN_CHARADDED, GeanyScintilla.SCN_AUTOCSELECTION):
            self.complete_python(editor, nt.ch, getattr(nt, 'text', None))

    def complete_python(self, editor, char, text=None):
        #  self.win.hide()
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
        script = jedi.Script(buffer, line, col)
        if not script:
            return
        completions = script.completions()
        if not completions:
            return
        word = ""
        #  self.store.clear()
        for complete in completions:
            name = complete.name
            if name.startswith('__'):
                continue
            #  self.store.append([name])
            word += "{}\n".format(name)
        sci.send_command(GeanyScintilla.SCI_AUTOCCANCEL)
        word = ctypes.c_wchar_p(word)
        #  word = ctypes.c_char_p(word.encode('utf8'))
            #  word = Geany.encodings_convert_to_utf8(word, -1)
        sci.send_message(GeanyScintilla.SCI_AUTOCSHOW, rootlen, ctypes.cast(word, ctypes.c_void_p).value)
        #  self.win.show_all()

    def configure(self, dialog):
        vbox = Gtk.VBox(spacing=6)
        vbox.set_border_width(6)
        check_highlight = Gtk.CheckButton(_("Highlight Matching Tags"))
        if self.highlight_tag:
            check_highlight.set_active(True)
        check_highlight.connect("toggled", self.on_highlight_tag_toggled)
        check_editor_menu = Gtk.CheckButton(_("Show some actions on editor menu"))
        if self.show_editor_menu:
            check_editor_menu.set_active(True)
        check_editor_menu.connect("toggled", self.on_editor_menu_toggled)
        check_specific_menu = Gtk.CheckButton(_("Attach menu to menubar rather than tools menu."))
        if self.show_specific_menu:
            check_specific_menu.set_active(True)
        check_specific_menu.connect("toggled", self.on_specific_menu_toggled)
        vbox.pack_start(check_highlight, True, True, 0)
        vbox.pack_start(check_editor_menu, True, True, 0)
        vbox.pack_start(check_specific_menu, True, True, 0)
        return vbox
