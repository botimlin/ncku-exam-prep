CC     ?= cc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
B      := build

$(B)/device: device_main.c pico_shim.c compute.c pico_shim.h compute.h
	@mkdir -p $(B)
	$(CC) $(CFLAGS) -o $@ device_main.c pico_shim.c compute.c

.PHONY: clean
clean:
	rm -rf $(B)
