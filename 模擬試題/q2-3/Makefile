CC     ?= cc
CFLAGS ?= -O2 -Wall -Wextra -std=c11 -pthread
B      := build
SRCS   := main.c work.c pico_sim/pico_sim.c
HDRS   := work.h pico_sim/pico_sim.h

.PHONY: all run tsan clean
all: $(B)/pipeline

$(B)/pipeline: $(SRCS) $(HDRS)
	@mkdir -p $(B)
	$(CC) $(CFLAGS) -o $@ $(SRCS)

run: $(B)/pipeline
	./$(B)/pipeline

# ThreadSanitizer：會指出兩個核心同時存取、又沒有被鎖保護的變數
tsan: $(SRCS) $(HDRS)
	@mkdir -p $(B)
	$(CC) -O1 -g -Wall -std=c11 -pthread -fsanitize=thread -o $(B)/pipeline_tsan $(SRCS)
	TSAN_OPTIONS=report_thread_leaks=0 ./$(B)/pipeline_tsan

clean:
	rm -rf $(B)
