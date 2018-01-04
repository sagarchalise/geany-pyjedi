/*
 *      demoplugin.c - this file is part of Geany, a fast and lightweight IDE
 *
 *      Copyright 2007-2012 Enrico Tröger <enrico(dot)troeger(at)uvena(dot)de>
 *      Copyright 2007-2012 Nick Treleaven <nick(dot)treleaven(at)btinternet(dot)com>
 *
 *      This program is free software; you can redistribute it and/or modify
 *      it under the terms of the GNU General Public License as published by
 *      the Free Software Foundation; either version 2 of the License, or
 *      (at your option) any later version.
 *
 *      This program is distributed in the hope that it will be useful,
 *      but WITHOUT ANY WARRANTY; without even the implied warranty of
 *      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *      GNU General Public License for more details.
 *
 *      You should have received a copy of the GNU General Public License along
 *      with this program; if not, write to the Free Software Foundation, Inc.,
 *      51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

/**
 * Demo plugin - example of a basic plugin for Geany. Adds a menu item to the
 * Tools menu.
 *
 * Note: This is not installed by default, but (on *nix) you can build it as follows:
 * cd plugins
 * make demoplugin.so
 *
 * Then copy or symlink the plugins/demoplugin.so file to ~/.config/geany/plugins
 * - it will be loaded at next startup.
 */


// #include <stdio.h>
// #include <sys/stat.h>
#include "geanyplugin.h"	/* plugin API, always comes first */
#include "Scintilla.h"	/* for the SCNotification struct */
#include "Python.h"
// gchar *default_paths = "/usr/lib/python2.7/site-packages:/usr/lib/python2.7/dist-packages:/usr/lib/python2.7:/usr/local/lib/python2.7:/usr/local/lib/python2.7/site-packages:/usr/local/lib/python2.7/dist-packages:/usr/lib/python2.7/site-packages:/usr/lib/python2.7/dist-packages:/usr/local/lib/geany:/usr/local/lib/geany/geanypy:/home/sagar/.config/geany/plugins";
gchar *default_include = NULL;
static gchar *CONFIG_FILE = NULL;

static void jedi_init_python(void)
{

	if (!Py_IsInitialized())
		Py_Initialize();
        // if (!is_path_set){
                // PySys_SetPath(default_paths);
                // is_path_set = TRUE;
        // }
        
}
static void append_path(gchar *add_path){
        // if (project != NULL || DOC_VALID(doc));
        jedi_init_python();
        PyObject *sys_path;
        gchar *rep = NULL;
        sys_path = PySys_GetObject("path");
        if (PyList_Check(sys_path)){
                g_free(rep);
                rep = (gchar *)PyObject_Str(sys_path);
                if(g_strrstr(rep, add_path) == NULL){
                        msgwin_status_add("Jedi Path Added: %s", add_path);
                        Py_XINCREF(sys_path);
                        PyList_Append(sys_path, Py_BuildValue("s", add_path));        
                }
        }
        Py_XDECREF(sys_path);
}
static void show_autocomplete(ScintillaObject *sci, gsize rootlen, GString *words)
{
	/* hide autocompletion if only option is already typed */
	if (rootlen >= words->len ||
		(words->str[rootlen] == '?' && rootlen >= words->len - 2))
	{
		sci_send_command(sci, SCI_AUTOCCANCEL);
		return;
	}
	scintilla_send_message(sci, SCI_AUTOCSHOW, rootlen, (sptr_t) words->str);
}

static void complete_python(PyObject *module, GeanyEditor *editor, int ch, const gchar *text){
        Py_ssize_t list_size;
        gint line, col, pos, rootlen;
        gboolean import_check = FALSE;
	ScintillaObject *sci;
        const gchar *pname;
        gchar *word_at_pos, *buffer;
        PyObject *script, *completion, *complete, *name, *cls, *args, *docstring;
	g_return_if_fail(editor !=NULL);
        if (text == NULL){
                
        switch(ch){
                case '\r':
		case '\n':
		case '>':
		case '/':
		case '(':
		case ')':
		case '{':
		case '[':
		case '"':
		case '\'':
		case '}':
		case ':':
                        return;
        }
        
        }
	/* If we are at the beginning of the document, we skip autocompletion as we can't determine the
	 * necessary styling information */
	sci = editor->sci;
        pos = sci_get_current_position(sci);
        line = sci_get_current_line(sci)+1;
        word_at_pos = g_strchug(sci_get_line(sci, line-1));
        if(g_str_has_prefix(word_at_pos, "import") || g_str_has_prefix(word_at_pos, "from")){
                buffer = sci_get_line(sci, line-1);
                line = 1;
                import_check = TRUE;
        } 
        else{
             buffer = sci_get_contents_range(sci, 0, pos);
                
        }              
        g_free(word_at_pos);
        word_at_pos = editor_get_word_at_pos(editor, pos, GEANY_WORDCHARS".");
        if(word_at_pos == NULL){
                return;
        }
        col = sci_get_col_from_position(sci, pos);
        rootlen = strlen(word_at_pos);
        if (strstr(word_at_pos, ".") != NULL){
                g_free(word_at_pos);
                word_at_pos = editor_get_word_at_pos(editor, pos, NULL);
                if(word_at_pos == NULL){
                        rootlen = 0;
                }
                else{
                        rootlen = strlen(word_at_pos);
                        g_free(word_at_pos);
                }
        }
        else if((!import_check && rootlen < 2) || rootlen == 0 ){
                g_free(word_at_pos);
                return;
        }
        PyRun_SimpleString("import jedi");
        PyRun_SimpleString("jedi.settings.case_insensitive_completion=False");
        cls = PyObject_GetAttrString(module, "Script");
        if (cls == NULL)
	{
		if (PyErr_Occurred())
			PyErr_Print();
		Py_XDECREF(cls);
		Py_XDECREF(module);
		return;
	}
        args = Py_BuildValue("(u,i,i)", buffer, line, col);
        script = PyObject_CallObject(cls, args);
        
	if (script == NULL)
	{
		if (PyErr_Occurred())
			PyErr_Print();
                Py_XDECREF(module);
                Py_XDECREF(cls);
                Py_XDECREF(script);
		Py_XDECREF(args);
		return;
	}
	Py_XDECREF(args);
        completion = PyObject_CallMethod(script, "completions", NULL);
        if (completion == NULL)
	{
		if (PyErr_Occurred())
			PyErr_Print();
		Py_XDECREF(completion);
                Py_XDECREF(module);
                Py_XDECREF(cls);
                Py_XDECREF(script);
		Py_XDECREF(args);
		return;
	} 
        if (!PyList_Check(completion))
	{
		if (PyErr_Occurred())
			PyErr_Print();
		Py_XDECREF(completion);
		return;
	}
    if (PyErr_Occurred()){
        Py_XDECREF(completion);
        Py_XDECREF(module);
        Py_XDECREF(cls);
        Py_XDECREF(script);
		Py_XDECREF(args);
        return;
}
        list_size = PyList_GET_SIZE(completion);
        if(list_size > 0){
                GString *words = g_string_sized_new(100);
        for(int i=0; i<list_size; i++){
                if (PyErr_Occurred()){
                    Py_XDECREF(completion);
                    Py_XDECREF(module);
                    Py_XDECREF(cls);
                    Py_XDECREF(script);
                    Py_XDECREF(args);
                    return;
                }
                complete = PyList_GET_ITEM(completion, i);
                if (complete == NULL)
                {
                        if (PyErr_Occurred())
                                PyErr_Print();
                        Py_XDECREF(complete);
                        continue;
                }
                name = PyObject_GetAttrString(complete, "name");
                if (name == NULL)
                {
                        if (PyErr_Occurred())
                                PyErr_Print();
                        Py_XDECREF(complete);
                        Py_XDECREF(name);
                        continue;
                }
                pname = (const gchar *)PyString_AsString(name);
                if(text != NULL){
                        if(!utils_str_equal(pname, text))
                                continue;
                        docstring = PyObject_CallMethod(complete, "docstring", NULL);
                        if(docstring == NULL){
                                break;
                        }
                        else{
                                pname = (const gchar *)PyString_AsString(docstring);
                                if (strlen(pname) > 0){
                                        g_string_append(words, "Doc:\n");
                                        g_string_append(words, pname);
                                }
                                Py_XDECREF(docstring);
                                break;
                        }
                }
                else{
                        if(g_str_has_prefix(pname, "__") && g_str_has_suffix(pname, "__")){
                                continue;
                        }
                        if (i > 0) 
                                g_string_append_c(words, '\n');
                        if (i == 15)
			{
				g_string_append(words, "...");
				break;
			}
                }
                g_string_append(words, pname);
                }
                
                msgwin_clear_tab(MSG_MESSAGE);
                if(text == NULL){
                        show_autocomplete(sci, rootlen, words);
                }
                else{
                        if(words->len > 6){
                                msgwin_msg_add(COLOR_BLACK, line-1, editor->document, "%s", words->str);
                                msgwin_switch_tab(MSG_MESSAGE, FALSE);
                        }
                }
                
                g_string_free(words, TRUE);
        } 
        g_free(buffer);
        
}
static gboolean on_editor_notify(GObject *object, GeanyEditor *editor,
								 SCNotification *nt, gpointer data)
{
	/* data == GeanyPlugin because the data member of PluginCallback was set to NULL
	 * and this plugin has called geany_plugin_set_data() with the GeanyPlugin pointer as
	 * data */
	GeanyPlugin *plugin = data;
        GeanyDocument *doc = document_get_current();
        gint lexer, pos, style;
        PyObject *module;
        if(!DOC_VALID(doc)){
                return FALSE;
        }
        if(doc->file_type->id != GEANY_FILETYPES_PYTHON){
                return FALSE;
        }
	/* For detailed documentation about the SCNotification struct, please see
	 * http://www.scintilla.org/ScintillaDoc.html#Notifications. */
        pos = sci_get_current_position(editor->sci);
	if (G_UNLIKELY(pos < 2))
		return FALSE;
        lexer = sci_get_lexer(editor->sci);
	style = sci_get_style_at(editor->sci, pos - 2);

	/* don't autocomplete in comments and strings */
	if (!highlighting_is_code_style(lexer, style))
		return FALSE;
        jedi_init_python();
        
        module = PyImport_ImportModule("jedi");
        if (module == NULL)
	{
		if (PyErr_Occurred())
			PyErr_Print();
		Py_XDECREF(module);
                return FALSE;
	}
	switch (nt->nmhdr.code)
	{
		case SCN_CHARADDED:
                        complete_python(module, editor, nt->ch, NULL);
                        break;
                case SCN_AUTOCSELECTION:
                        complete_python(module, editor, nt->ch, nt->text);
                        break;
	}

	return FALSE;
}
static gboolean on_project_open(GObject *obj, GKeyFile *config, gpointer data)
{
        GeanyPlugin *plugin = data;
        GeanyProject *project = plugin->geany_data->app->project;
	if(project != NULL){
                append_path(project->base_path);
        }
}
static PluginCallback demo_callbacks[] =
{
	/* Set 'after' (third field) to TRUE to run the callback @a after the default handler.
	 * If 'after' is FALSE, the callback is run @a before the default handler, so the plugin
	 * can prevent Geany from processing the notification. Use this with care. */
        {"project-open", (GCallback) & on_project_open, FALSE, NULL},
        // {"project-open", (GCallback) & on_project_open, TRUE, NULL},
	{ "editor-notify", (GCallback) &on_editor_notify, FALSE, NULL },
	{ NULL, NULL, FALSE, NULL }
};


/* Callback when the menu item is clicked. */
// static void
// item_activate(GtkMenuItem *menuitem, gpointer gdata)
// {
	// GtkWidget *dialog;
	// GeanyPlugin *plugin = gdata;
	// GeanyData *geany_data = plugin->geany_data;

	// dialog = gtk_message_dialog_new(
		// GTK_WINDOW(geany_data->main_widgets->window),
		// GTK_DIALOG_DESTROY_WITH_PARENT,
		// GTK_MESSAGE_INFO,
		// GTK_BUTTONS_OK,
		// "%s", default_include);
	// gtk_message_dialog_format_secondary_text(GTK_MESSAGE_DIALOG(dialog),
		// _("(From the %s plugin)"), plugin->info->name);

	// gtk_dialog_run(GTK_DIALOG(dialog));
	// gtk_widget_destroy(dialog);
// }


/* Called by Geany to initialize the plugin */
static gboolean demo_init(GeanyPlugin *plugin, gpointer data)
{
	GeanyData *geany_data = plugin->geany_data;
        CONFIG_FILE = g_strconcat(geany_data->app->configdir, G_DIR_SEPARATOR_S, "plugins",
                        G_DIR_SEPARATOR_S, "pyjedi.conf", NULL);
        geany_plugin_set_data(plugin, plugin, NULL);
        GKeyFile *config 	= g_key_file_new();

	g_key_file_load_from_file(config, CONFIG_FILE, G_KEY_FILE_NONE, NULL);

	default_include = utils_get_setting_string(config, "pyjedi", "path", NULL);
        if (default_include != NULL){
                append_path(default_include);
        }
        g_key_file_free(config);
	return TRUE;
}


static void
on_configure_response(GtkDialog *dialog, gint response, gpointer user_data)
{
	/* catch OK or Apply clicked */
	if (response == GTK_RESPONSE_APPLY || response == GTK_RESPONSE_OK)
	{
		/* We only have one pref here, but for more you would use a struct for user_data */
		GtkWidget *entry = GTK_WIDGET(user_data);
                const gchar *input_path = gtk_entry_get_text(GTK_ENTRY(entry));
                if (default_include != NULL && utils_str_equal(input_path, default_include)){
                        return;
                }
                g_free(default_include);
                default_include = g_strdup(input_path);
                if(input_path != NULL){
                        g_free(input_path);
                }
                if (default_include == NULL){
                        return;
                }
                if (!g_file_test(default_include, G_FILE_TEST_IS_DIR))
                        return;
                append_path(default_include);
                /* maybe the plugin should write here the settings into a file
		 * (e.g. using GLib's GKeyFile API)
		 * all plugin specific files should be created in:
                geany->app->configdir G_DIR_SEPARATOR_S plugins G_DIR_SEPARATOR_S pluginname G_DIR_SEPARATOR_S
		 * e.g. this could be: ~/.config/geany/plugins/Demo/, please use geany->app->configdir */
                 GKeyFile 	*config 		= g_key_file_new();
                gchar 		*config_dir 	= g_path_get_dirname(CONFIG_FILE);
                gchar 		*data;

                g_key_file_load_from_file(config, CONFIG_FILE, G_KEY_FILE_NONE, NULL);
                if (! g_file_test(config_dir, G_FILE_TEST_IS_DIR) && utils_mkdir(config_dir, TRUE) != 0)
                {
                        g_free(config_dir);
                        g_key_file_free(config);
                        return FALSE;
                }

                g_key_file_set_string(config, 	"pyjedi", "path", default_include);
                data = g_key_file_to_data(config, NULL, NULL);
                utils_write_file(CONFIG_FILE, data);
                g_free(data);

                g_free(config_dir);
                g_key_file_free(config);
        }
}

/* Called by Geany to show the plugin's configure dialog. This function is always called after
 * demo_init() was called.
 * You can omit this function if the plugin doesn't need to be configured.
 * Note: parent is the parent window which can be used as the transient window for the created
 *       dialog. */
static GtkWidget *demo_configure(GeanyPlugin *plugin, GtkDialog *dialog, gpointer data)
{
        
	GtkWidget *label, *entry, *vbox;

	/* example configuration dialog */
	vbox = gtk_vbox_new(FALSE, 6);

	/* add a label and a text entry to the dialog */
	label = gtk_label_new(_("Extra Path to Include with jedi:"));
	gtk_misc_set_alignment(GTK_MISC(label), 0, 0.5);
	entry = gtk_entry_new();
	if (default_include != NULL)
		gtk_entry_set_text(GTK_ENTRY(entry), default_include);

	gtk_container_add(GTK_CONTAINER(vbox), label);
	gtk_container_add(GTK_CONTAINER(vbox), entry);

	gtk_widget_show_all(vbox);

	/* Connect a callback for when the user clicks a dialog button */
	g_signal_connect(dialog, "response", G_CALLBACK(on_configure_response), entry);
	return vbox;
}


/* Called by Geany before unloading the plugin.
 * Here any UI changes should be removed, memory freed and any other finalization done.
 * Be sure to leave Geany as it was before demo_init(). */
static void demo_cleanup(GeanyPlugin *plugin, gpointer data)
{
	// /* remove the menu item added in demo_init() */
	// gtk_widget_destroy(main_menu_item);
	// /* release other allocated strings and objects */
	g_free(default_include);
        g_free(CONFIG_FILE);
        //Py_Finalize();
}

void geany_load_module(GeanyPlugin *plugin)
{
	/* main_locale_init() must be called for your package before any localization can be done */
	main_locale_init(LOCALEDIR, GETTEXT_PACKAGE);
	plugin->info->name = _("Python Jedi Complete");
	plugin->info->description = _("Trial Jedi Complete.");
	plugin->info->version = "0.1";
	plugin->info->author =  _("Sagar Chalise");

	plugin->funcs->init = demo_init;
	plugin->funcs->configure = demo_configure;
	plugin->funcs->help = NULL; /* This demo has no help but it is an option */
	plugin->funcs->cleanup = demo_cleanup;
	plugin->funcs->callbacks = demo_callbacks;

	GEANY_PLUGIN_REGISTER(plugin, 225);
}
