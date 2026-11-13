"""link.py — 打開序列埠（不用改）。

真的 Pico 是 /dev/ttyACM0；模擬時是 tools/fake_link.py 印出來的 /dev/pts/N。
這裡不用 pyserial（考前練習的容器沒有裝），直接用 os + termios，效果一樣。
"""
import os
import termios
import tty


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(fd)                      # raw：不轉換 \n、不 echo
    attrs = termios.tcgetattr(fd)
    attrs[6][termios.VMIN] = 1          # read() 至少等到 1 byte
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd
