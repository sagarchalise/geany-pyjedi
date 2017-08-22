libdir.x86_64 := $(shell if [ -d "/usr/lib/x86_64-linux-gnu" ]; then echo "/usr/lib/x86_64-linux-gnu"; else echo "/usr/lib64"; fi )
libdir.i686   := $(shell if [ -d "/usr/lib/i386-linux-gnu" ]; then echo "/usr/lib/i386-linux-gnu"; else echo "/usr/lib"; fi )

MACHINE := $(shell uname -m)

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
