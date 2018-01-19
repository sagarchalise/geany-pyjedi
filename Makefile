all: build
	
build:	
	gcc -DLOCALEDIR=\"\" -DGETTEXT_PACKAGE=\"pyjedi\" -c ./pyjedi.c -fPIC `pkg-config --cflags geany python3`
	gcc pyjedi.o -o pyjedi.so -shared `pkg-config --libs geany python3`

install: uninstall startinstall

startinstall:
	cp -f ./pyjedi.so ~/.config/geany/plugins
	chmod 755 ~/.config/geany/plugins/pyjedi.so

uninstall:
	rm -f ~/.config/geany/plugins/pyjedi.so

clean:
	rm -f ./pyjedi.so
	rm -f ./pyjedi.o
