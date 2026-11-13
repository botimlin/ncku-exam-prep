CC     ?= cc
CFLAGS ?= -O2 -Wall -Wextra -std=c11
B      := build

.PHONY: test pio clean
test: $(B)/public_test
	./$(B)/public_test

$(B)/public_test: public_test.c packet.c rv_imm.c packet.h rv_imm.h
	@mkdir -p $(B)
	$(CC) $(CFLAGS) -o $@ public_test.c packet.c rv_imm.c

pio:
	python3 ../tools/pio_sim.py pio/unpack8.pio 0x44332211 0xddccbbaa

clean:
	rm -rf $(B)
