CFLAGS ?= -O2 -Wall -Wextra -Werror
LDFLAGS ?=

all: pam_opd2413_face.so

pam_opd2413_face.so: pam_opd2413_face.c
	$(CC) $(CFLAGS) -fPIC -shared $(LDFLAGS) \
		$(shell pkg-config --cflags libsystemd) \
		-o $@ $< \
		-lpam $(shell pkg-config --libs libsystemd)

clean:
	rm -f pam_opd2413_face.so
