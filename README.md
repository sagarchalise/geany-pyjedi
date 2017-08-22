# geany-pyjedi

Python completion with jedi.


*Adds project path on project open

*Also a functionality to configure a path on session.


Requires `jedi` && Python C headers.
`pip install jedi`


$ gcc -DLOCALEDIR=\"\" -DGETTEXT_PACKAGE=\"geany-pyjedi\" -c pyjedi.c -fPIC `pkg-config --cflags geany python-2.7`

$ gcc pyjedi.o -o pyjedi.so -shared `pkg-config --libs geany python-2.7`


**Copy pyjedi.so to plugin path**
