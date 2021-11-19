#!/usr/bin/env python

import json
import sys
import time
import threading
from functools import lru_cache
from collections import defaultdict
from contextlib import contextmanager

import Xlib
import Xlib.display
from Xlib import X
from pynput import mouse
from pynput import keyboard
from ewmh import EWMH as _EWMH
import psutil


def b2s(value):
    if not value:
        return
    return value.decode('utf-8')


def log(event, data):
    _data = {'time': time.time(), 'v': 'a', 'event': event, 'data': data}
    sys.stdout.write(json.dumps(_data, indent=None, ensure_ascii=False))
    sys.stdout.write('\n')
    sys.stdout.flush()


@lru_cache(maxsize=256)
def cmdline_by_pid(pid):
    process = psutil.Process(pid)
    value = process.cmdline()
    log('new-pid', {'pid': pid, 'cmdline': value})
    return value


class EWMH(_EWMH):
    def getWmClass(self, win):
        value = self._getProperty('WM_CLASS', win) or b''
        value = value.split(b'\x00')
        return list(map(b2s, filter(lambda v: v, value)))

    def isWmFullscreen(self, win):
        return bool(self.getWmState(win, '_NET_WM_STATE_FULLSCREEN'))

    def getWmName(self, win):
        return b2s(super(EWMH, self).getWmName(win))

    def getWmPid(self, win):
        try:
            return super(EWMH, self).getWmPid(win)
        except TypeError:
            pass

    def window_options(self, win):
        if not win:
            return
        try:
            pid = self.getWmPid(win)
            if pid:
                cmdline_by_pid(pid)
            return {
                'name': self.getWmName(win),
                'wid': win.id,
                'pid': pid,
                'fullscreen': self.isWmFullscreen(win),
                'class': self.getWmClass(win),
            }
        except Xlib.error.BadWindow:
            pass


@contextmanager
def window_obj(display, win_id):
    """Simplify dealing with BadWindow (make it either valid or None)"""
    window_obj = None
    if win_id:
        try:
            window_obj = display.create_resource_object('window', win_id)
        except Xlib.error.XError:
            pass
    yield window_obj


class TimerThread(threading.Thread):
    def __init__(self, interval, callback):
        super(TimerThread, self).__init__()
        self.daemon = True
        self.interval = interval
        self.callback = callback

    def run(self):
        while True:
            time.sleep(self.interval)
            self.callback()


class Activity(object):
    def __init__(self):
        self.ewmh = EWMH()
        self.window_details = None
        self.last_window = None
        self.keyboard_listener = None
        self.mouse_listener = None
        self.input_stat = defaultdict(int)
        self.thread_lock = threading.Lock()
        self.timer_thread = None
        self.input_flush_interval = 20

    def update_input_stat(self, key):
        with self.thread_lock:
            self.input_stat[key] += 1

    def flush_input_stat(self, timeout=True):
        if not self.input_stat:
            return
        with self.thread_lock:
            data = {
                'timeout': timeout,
                'stats': self.input_stat,
            }
            if timeout:
                data['interval'] = self.input_flush_interval
            log('input', data)
            self.input_stat = defaultdict(int)

    def on_press(self, _key):
        self.update_input_stat('press')

    def on_release(self, _key):
        self.update_input_stat('release')

    def on_move(self, _x, _y):
        self.update_input_stat('move')

    def on_click(self, _x, _y, _button, _pressed):
        self.update_input_stat('click')

    def on_scroll(self, _x, _y, _dx, _dy):
        self.update_input_stat('scroll')

    def start(self):
        display = Xlib.display.Display()
        root = display.screen().root

        event_mask = X.PropertyChangeMask
        root.change_attributes(event_mask=event_mask)

        self.timer_thread = TimerThread(self.input_flush_interval,
                                        self.flush_input_stat)
        self.timer_thread.start()

        self.keyboard_listener = keyboard.Listener(on_press=self.on_press,
                                                   on_release=self.on_release)
        self.keyboard_listener.start()

        self.mouse_listener = mouse.Listener(on_move=self.on_move,
                                             on_click=self.on_click,
                                             on_scroll=self.on_scroll)
        self.mouse_listener.start()

        # last_window = None
        self.process_window(display)
        while True:
            _event = display.next_event()
            self.process_window(display)

    def process_window(self, display):
        active_window = self.ewmh.getActiveWindow()
        if active_window != self.last_window:
            with window_obj(display, self.last_window) as win:
                if win:
                    win.change_attributes(event_mask=X.NoEventMask)
            with window_obj(display, active_window) as win:
                if win:
                    win.change_attributes(event_mask=X.PropertyChangeMask)

        self.handle_window(active_window)
        self.last_window = active_window

    def handle_window(self, win):
        window_details = self.ewmh.window_options(win)
        if window_details != self.window_details:
            self.flush_input_stat(timeout=False)
            log('active-window', window_details)
            self.window_details = window_details


def main():
    try:
        Activity().start()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
