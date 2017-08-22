all: build
	
build:	
	gcc -DLOCALEDIR=\"\" -DGETTEXT_PACKAGE=\"pyjedi\" -c ./pyjedi.c -fPIC `pkg-config --cflags geany python-2.7`
	gcc pyjedi.o -o pyjedi.so -shared `pkg-config --libs geany python-2.7`

install: uninstall startinstall

startinstall:
	cp -f ./pyjedi.so ~/.config/geany/plugins
	chmod 755 ~/.config/geany/plugins/pyjedi.so

uninstall:
	rm -f ~/.config/geany/plugins/pyjedi*

clean:
	rm -f ./pyjedi.so
	rm -f ./pyjedi.o
