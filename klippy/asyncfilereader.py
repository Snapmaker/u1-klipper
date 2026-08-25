import os
import queue
import threading
import time
import logging

try:
    from json_compat import loads as _json_loads
except Exception:
    import json as _stdlib_json
    _json_loads = _stdlib_json.loads


def _pread(fd, size, offset):
    if hasattr(os, 'pread'):
        return os.pread(fd, size, offset)
    os.lseek(fd, offset, os.SEEK_SET)
    return os.read(fd, size)


def _trailing_incomplete_utf8(b):
    if not b:
        return 0
    i = len(b) - 1
    if b[i] < 0x80:
        return 0
    cont = 0
    while i >= 0 and (b[i] & 0xC0) == 0x80:
        cont += 1
        i -= 1
    if i < 0:
        return cont
    lead = b[i]
    if 0xC0 <= lead <= 0xF7:
        if lead >= 0xF0:
            expect = 4
        elif lead >= 0xE0:
            expect = 3
        elif lead >= 0xC0:
            expect = 2
        else:
            return cont
        have = cont + 1
        return have if have < expect else 0
    return cont

TARGET_AHEAD = 128 * 1024
READAHEAD_CHUNK = 64 * 1024
BUF_HARD_LIMIT = 2 * TARGET_AHEAD
SLOW_THRESHOLD = 0.020
TOUCH_BACKOFF = 0.002
POLL_BACKOFF = 0.01
LOOP_IDLE_WAIT = 0.002
DEFAULT_READ_TIMEOUT = 30.0


class _ReadRequest:
    def __init__(self, path, parse_json=False, op='read', exts=None, recursive=False):
        self.path = path
        self.parse_json = parse_json
        self.op = op
        self.exts = exts
        self.recursive = recursive
        self.result = None
        self.error = None
        self.done = threading.Event()


class _CloseCommand:
    def __init__(self, fd, reader):
        self.fd = fd
        self.reader = reader


class AsyncFileReader:

    def __init__(self, path, reactor):
        self.name = path
        self._reactor = reactor
        self._fd = os.open(path, os.O_RDONLY)
        try:
            self.size = os.fstat(self._fd).st_size
        except Exception:
            logging.exception("asyncfilereader: fstat failed for %s", path)
            os.close(self._fd)
            raise
        self._buf = b""
        self._buf_start = 0
        self.read_pos = 0
        self._gen = 0
        self.eof = False
        self._error = None
        self._closed = False
        self._logged_first_read = False
        self._empty_retries = 0
        self._lock = threading.Lock()
        try:
            reader = get_async_file_reader()
            reader._register_gcode(self)
        except Exception:
            logging.exception("asyncfilereader: registration failed for %s", path)
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
            self._closed = True
            raise

    def read(self, n=8192):
        if self._error is not None:
            raise self._error
        if self._closed:
            return ''
        if n <= 0:
            return ''
        while True:
            with self._lock:
                if self._error is not None:
                    raise self._error
                if self._closed:
                    return ''
                if self._buf:
                    take = self._buf[:n]
                    keep = _trailing_incomplete_utf8(take)
                    if keep > 0:
                        if keep < len(take):
                            take = take[:-keep]
                        else:
                            first = self._buf[0]
                            if first >= 0xF0:
                                need = 4
                            elif first >= 0xE0:
                                need = 3
                            elif first >= 0xC0:
                                need = 2
                            else:
                                need = 1
                            if len(self._buf) >= need:
                                take = self._buf[:need]
                            elif self.eof:
                                take = self._buf[:n]
                            else:
                                take = b''
                    if take:
                        self.read_pos += len(take)
                        self._buf = self._buf[len(take):]
                        self._buf_start = self.read_pos
                        self._empty_retries = 0
                        try:
                            return take.decode('utf-8')
                        except UnicodeDecodeError as e:
                            self._error = e
                            raise
                    if self.eof:
                        take = self._buf[:n]
                        self.read_pos += len(take)
                        self._buf = self._buf[len(take):]
                        self._buf_start = self.read_pos
                        self._empty_retries = 0
                        try:
                            return take.decode('utf-8')
                        except UnicodeDecodeError as e:
                            self._error = e
                            raise
                elif self.eof:
                    return ''
                self._empty_retries += 1
                if self._empty_retries % 1000 == 0:
                    logging.warning("[asyncio] read stalled %d retries pos=%d eof=%s err=%s",
                                    self._empty_retries, self.read_pos, self.eof, self._error)
                mr = _MainReader
                if mr is not None:
                    mr.buf_empty += 1
            self._reactor.pause(self._reactor.monotonic() + TOUCH_BACKOFF)

    def seek(self, pos):
        if self._closed:
            raise IOError("seek on closed AsyncFileReader")
        with self._lock:
            self.read_pos = pos
            self._buf = b""
            self._buf_start = pos
            self._gen += 1
            self.eof = False
            self._error = None
            self._empty_retries = 0

    def tell(self):
        return self.read_pos

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            fd = self._fd
            self._fd = None
        reader = _MainReader
        if reader is not None:
            try:
                reader._enqueue_close(_CloseCommand(fd, self))
            except Exception:
                logging.exception("asyncfilereader: enqueue close failed")
                try:
                    if fd is not None:
                        os.close(fd)
                except Exception:
                    pass
        else:
            try:
                if fd is not None:
                    os.close(fd)
            except Exception:
                pass

    def __del__(self):
        try:
            if not self._closed:
                self.close()
        except Exception:
            pass


class AsyncFileIO:

    def __init__(self, reader):
        self._reader = reader

    def submit_read(self, path, parse_json=False):
        req = _ReadRequest(path, parse_json=parse_json, op='read')
        self._reader._enqueue_read(req)
        return req

    def submit_listdir(self, path, exts=None, recursive=False):
        req = _ReadRequest(path, op='listdir', exts=exts, recursive=recursive)
        self._reader._enqueue_read(req)
        return req

    def poll(self, req):
        if not req.done.is_set():
            return None
        if req.error is not None:
            return (False, req.error)
        return (True, req.result)

    def wait(self, req, reactor, timeout=DEFAULT_READ_TIMEOUT):
        deadline = reactor.monotonic() + timeout
        while not req.done.is_set():
            if reactor.monotonic() > deadline:
                raise TimeoutError("async file read timeout: %s" % req.path)
            reactor.pause(reactor.monotonic() + POLL_BACKOFF)
        if req.error is not None:
            raise req.error
        return req.result


class _AsyncFileReaderSingleton:

    def __init__(self):
        self._read_queue = queue.Queue()
        self._close_queue = queue.Queue()
        self._gcode = None
        self._gcode_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="asyncfilereader", daemon=True)
        self.slow_ops = 0
        self.slow_max = 0.0
        self.buf_empty = 0
        self.gen_discard = 0
        self.discontinuity = 0
        self.bg_errors = 0

    def start(self):
        self._thread.start()
        logging.info("asyncfilereader: read thread started (tid=%s)", self._thread.ident)

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        if not self._thread.is_alive():
            while True:
                try:
                    cmd = self._close_queue.get_nowait()
                    self._handle_close(cmd)
                except queue.Empty:
                    break
        logging.info("asyncfilereader: read thread stopped")

    def _register_gcode(self, reader):
        with self._gcode_lock:
            if self._gcode is not None and self._gcode is not reader \
                    and not self._gcode._closed:
                try:
                    old = self._gcode
                    with old._lock:
                        old._closed = True
                        fd = old._fd
                        old._fd = None
                    self._close_queue.put(_CloseCommand(fd, old))
                    logging.info("asyncfilereader: replaced stale gcode reader")
                except Exception:
                    logging.exception("asyncfilereader: stale gcode cleanup")
            self._gcode = reader
            logging.info("asyncfilereader: gcode reader registered (path=%s size=%d)",
                          reader.name, reader.size)

    def _enqueue_read(self, req):
        self._read_queue.put(req)

    def _enqueue_close(self, cmd):
        self._close_queue.put(cmd)

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                try:
                    while True:
                        cmd = self._close_queue.get_nowait()
                        self._handle_close(cmd)
                except queue.Empty:
                    pass
                try:
                    req = self._read_queue.get_nowait()
                except queue.Empty:
                    req = None
                if req is not None:
                    self._handle_read(req)
                    continue
                if self._gcode is not None and not self._gcode._closed:
                    if self._maybe_readahead():
                        continue
                time.sleep(LOOP_IDLE_WAIT)
            except Exception:
                logging.exception("asyncfilereader: loop iteration failed")
                time.sleep(0.01)

    def _handle_close(self, cmd):
        try:
            if cmd.fd is not None:
                os.close(cmd.fd)
        except Exception:
            logging.exception("asyncfilereader: close fd failed")
        with self._gcode_lock:
            if self._gcode is cmd.reader:
                self._gcode = None

    def _handle_read(self, req):
        try:
            if req.op == 'listdir':
                req.result = self._do_listdir(req.path, req.exts, req.recursive)
            else:
                with open(req.path, 'rb') as f:
                    data = f.read()
                if req.parse_json:
                    req.result = _json_loads(data)
                else:
                    req.result = data
        except Exception as e:
            logging.warning("[asyncio] bg read failed: %s err=%s", req.path, e)
            req.error = e
            self.bg_errors += 1
        finally:
            req.done.set()

    def _do_listdir(self, dirname, exts, recursive):
        out = []
        if recursive:
            for root, dirs, files in os.walk(dirname, followlinks=True):
                for name in files:
                    if exts:
                        ext = name[name.rfind('.')+1:]
                        if ext not in exts:
                            continue
                    full_path = os.path.join(root, name)
                    r_path = full_path[len(dirname) + 1:]
                    size = os.path.getsize(full_path)
                    out.append((r_path, size))
        else:
            for fname in sorted(os.listdir(dirname), key=str.lower):
                if fname.startswith('.'):
                    continue
                full_path = os.path.join(dirname, fname)
                if not os.path.isfile(full_path):
                    continue
                if exts:
                    ext = fname[fname.rfind('.')+1:]
                    if ext not in exts:
                        continue
                size = os.path.getsize(full_path)
                out.append((fname, size))
        return sorted(out, key=lambda f: f[0].lower())

    def _maybe_readahead(self):
        g = self._gcode
        if g is None or g._error is not None or g.eof:
            return False
        with g._lock:
            if g._closed:
                return False
            fd = g._fd
            if fd is None:
                return False
            buf = g._buf
            buf_start = g._buf_start
            read_pos = g.read_pos
            gen = g._gen
        buffered = len(buf) - (read_pos - buf_start)
        if buffered < 0:
            buffered = 0
        if buffered >= TARGET_AHEAD:
            return False
        if len(buf) >= BUF_HARD_LIMIT:
            return False
        offset = buf_start + len(buf)
        to_read = min(READAHEAD_CHUNK, g.size - offset)
        if to_read <= 0:
            with g._lock:
                if not g._closed and gen == g._gen:
                    g.eof = True
            return False
        t0 = time.monotonic()
        try:
            data = _pread(fd, to_read, offset)
        except Exception as e:
            logging.warning("[asyncio] bg pread failed: offset=%d path=%s err=%s",
                            offset, g.name, e)
            with g._lock:
                if not g._closed and gen == g._gen:
                    g._error = e
            self.bg_errors += 1
            return True
        dt = (time.monotonic() - t0) * 1000.0
        if dt > SLOW_THRESHOLD * 1000:
            self.slow_ops += 1
            if dt > self.slow_max:
                self.slow_max = dt
            logging.warning("[asyncio] slow bg pread %.1fms offset=%d size=%d path=%s",
                            dt, offset, to_read, g.name)
        with g._lock:
            if g._closed or gen != g._gen:
                self.gen_discard += 1
                return True
            if not data:
                g.eof = True
                return True
            if offset == g._buf_start + len(g._buf):
                g._buf += data
                if not g._logged_first_read:
                    g._logged_first_read = True
                    logging.info("asyncfilereader: first pread ok (offset=%d len=%d)",
                                 offset, len(data))
            else:
                self.discontinuity += 1
                logging.warning("[asyncio] discontinuity drop offset=%d", offset)
            if offset + len(data) >= g.size:
                g.eof = True
        return True

    def stats(self):
        return (self.slow_ops, self.slow_max, self.buf_empty,
                self.gen_discard, self.discontinuity, self.bg_errors)


_MainReader = None
_Lock = threading.Lock()


def setup_async_file_reader():
    global _MainReader
    with _Lock:
        if _MainReader is None:
            _MainReader = _AsyncFileReaderSingleton()
            _MainReader.start()
    return _MainReader


def clear_async_file_reader():
    global _MainReader
    with _Lock:
        if _MainReader is not None:
            _MainReader.stop()
            _MainReader = None


def get_async_file_reader():
    if _MainReader is None:
        setup_async_file_reader()
    return _MainReader


def get_async_file_io():
    return AsyncFileIO(get_async_file_reader())
