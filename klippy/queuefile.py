import threading, queue, time, os, shutil, logging
from concurrent.futures import Future

QUEUE_SIZE = 1000
QUEUE_TIMEOUT = 1.0
DEFAULT_SYNC_TIMEOUT = 30.0

class FileOperationException(Exception):
    pass

class FileOperationTimeout(Exception):
    pass

class FileOperation:
    def __init__(self, op_type, filename, content=None, flush=False, sync=False, timeout=None, safe_write=False):
        self.op_type = op_type
        self.filename = filename
        self.content = content
        self.flush = flush
        self.sync = sync
        self.timeout = timeout or DEFAULT_SYNC_TIMEOUT
        self.safe_write = safe_write
        self.timestamp = time.time()
        self.future = Future() if sync else None
        self.result = None
        self.exception = None

class QueueHandler:
    def __init__(self, bg_queue):
        self.bg_queue = bg_queue

    def write_file(self, filename, content, flush=False, safe_write=False):
        op = FileOperation("write", filename, content, flush, False, None, safe_write)
        try:
            self.bg_queue.put_nowait(op)
        except queue.Full:
            raise FileOperationException("File operation queue is full")

    def delete_file(self, filename):
        op = FileOperation("delete", filename)
        try:
            self.bg_queue.put_nowait(op)
        except queue.Full:
            raise FileOperationException("File operation queue is full")

    def append_file(self, filename, content, flush=False, safe_write=False):
        op = FileOperation("append", filename, content, flush, False, None, safe_write)
        try:
            self.bg_queue.put_nowait(op)
        except queue.Full:
            raise FileOperationException("File operation queue is full")

class QueueListener:
    def __init__(self):
        self.bg_queue = queue.Queue(maxsize=QUEUE_SIZE)
        self.bg_thread = threading.Thread(target=self._bg_thread)
        self.handler = QueueHandler(self.bg_queue)
        self.bg_thread.start()

    def _bg_thread(self):
        while True:
            try:
                op = self.bg_queue.get(True)
                if op is None:
                    break
                self._process_operation(op)
                self.bg_queue.task_done()
            except Exception:
                continue

    def _process_operation(self, op):
        try:
            result = None
            exception = None

            if op.op_type == "write":
                directory = os.path.dirname(op.filename)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)

                if op.safe_write:
                    temp_filename = op.filename + ".tmp"
                    try:
                        with open(temp_filename, 'w') as f:
                            if op.content:
                                f.write(op.content)
                            # f.flush()
                            # os.fdatasync(f.fileno())
                        os.replace(temp_filename, op.filename)
                    except Exception:
                        if os.path.exists(temp_filename):
                            try:
                                os.remove(temp_filename)
                            except:
                                pass
                        raise
                else:
                    with open(op.filename, 'w') as f:
                        if op.content:
                            f.write(op.content)
                        # f.flush()
                        # os.fdatasync(f.fileno())
                result = True

            elif op.op_type == "delete":
                if os.path.exists(op.filename):
                    os.remove(op.filename)
                elif os.path.isdir(op.filename):
                    shutil.rmtree(op.filename)
                result = True

            elif op.op_type == "append" and op.content:
                directory = os.path.dirname(op.filename)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)

                if op.safe_write:
                    temp_filename = op.filename + ".tmp"
                    try:
                        original_content = ""
                        if os.path.exists(op.filename):
                            with open(op.filename, 'r') as f:
                                original_content = f.read()

                        with open(temp_filename, 'w') as f:
                            f.write(original_content)
                            f.write(op.content)
                            # f.flush()
                            # os.fdatasync(f.fileno())

                        os.replace(temp_filename, op.filename)
                    except Exception:
                        if os.path.exists(temp_filename):
                            try:
                                os.remove(temp_filename)
                            except:
                                pass
                        raise
                else:
                    with open(op.filename, 'a') as f:
                        f.write(op.content)
                        # f.flush()
                        # os.fdatasync(f.fileno())
                result = True

            if op.sync:
                if op.future:
                    if exception:
                        op.future.set_exception(exception)
                    else:
                        op.future.set_result(result)
                else:
                    op.result = result
                    op.exception = exception

        except Exception as e:
            exception = FileOperationException(f"File operation failed: {str(e)}")
            if op.sync:
                if op.future:
                    op.future.set_exception(exception)
                else:
                    op.exception = exception

    def write_file(self, filename, content, flush=False, safe_write=False):
        return self.handler.write_file(filename, content, flush, safe_write)

    def delete_file(self, filename):
        return self.handler.delete_file(filename)

    def append_file(self, filename, content, flush=False, safe_write=False):
        return self.handler.append_file(filename, content, flush, safe_write)

    def stop(self):
        self.bg_queue.put_nowait(None)
        self.bg_thread.join()

MainQueueHandler = None

def setup_bg_file_operations():
    global MainQueueHandler
    if MainQueueHandler is None:
        MainQueueHandler = QueueListener()
    return MainQueueHandler

def clear_bg_file_operations():
    global MainQueueHandler
    if MainQueueHandler is not None:
        MainQueueHandler.stop()
        MainQueueHandler = None

def async_write_file(filename, content, flush=False, safe_write=False):
    listener = setup_bg_file_operations()
    return listener.write_file(filename, content, flush, safe_write)

def async_delete_file(filename):
    listener = setup_bg_file_operations()
    return listener.delete_file(filename)

def async_append_file(filename, content, flush=False, safe_write=False):
    listener = setup_bg_file_operations()
    return listener.append_file(filename, content, flush, safe_write)

def sync_write_file(reactor, filename, content, flush=False, safe_write=False, timeout=None):
    listener = setup_bg_file_operations()
    op = FileOperation("write", filename, content, flush, sync=True, timeout=timeout or DEFAULT_SYNC_TIMEOUT, safe_write=safe_write)

    try:
        listener.handler.bg_queue.put(op, timeout=1.0)
    except queue.Full:
        raise FileOperationException("File operation queue is full")

    deadline = reactor.monotonic() + (timeout or DEFAULT_SYNC_TIMEOUT)

    while not op.future.done():
        if reactor.monotonic() > deadline:
            raise FileOperationTimeout("File operation timed out")

        reactor.pause(reactor.monotonic() + 0.01)
    return op.future.result()

def sync_delete_file(reactor, filename, timeout=None):
    listener = setup_bg_file_operations()
    op = FileOperation("delete", filename, None, False, sync=True, timeout=timeout or DEFAULT_SYNC_TIMEOUT)

    try:
        listener.handler.bg_queue.put(op, timeout=1.0)
    except queue.Full:
        raise FileOperationException("File operation queue is full")

    deadline = reactor.monotonic() + (timeout or DEFAULT_SYNC_TIMEOUT)

    while not op.future.done():
        if reactor.monotonic() > deadline:
            raise FileOperationTimeout("File operation timed out")

        reactor.pause(reactor.monotonic() + 0.01)
    return op.future.result()

def sync_delete_files_batch(reactor, filenames, timeout=None):
    """Submit all delete ops at once, then poll all futures together.
    Non-existent files are no-ops (the worker checks existence).
    Avoids per-file serial pause overhead."""
    listener = setup_bg_file_operations()
    timeout = timeout or DEFAULT_SYNC_TIMEOUT
    ops = []
    for filename in filenames:
        op = FileOperation("delete", filename, None, False, sync=True, timeout=timeout)
        try:
            listener.handler.bg_queue.put_nowait(op)
            ops.append(op)
        except queue.Full:
            logging.warning("sync_delete_files_batch: queue full, skip %s", filename)
    deadline = reactor.monotonic() + timeout
    for op in ops:
        while not op.future.done():
            if reactor.monotonic() > deadline:
                logging.warning("sync_delete_files_batch: timeout for %s", op.filename)
                break
            reactor.pause(reactor.monotonic() + 0.01)
    for op in ops:
        if op.future.done() and op.future.exception() is not None:
            logging.warning("sync_delete_files_batch: delete failed for %s: %s",
                            op.filename, op.future.exception())
    succeeded = sum(1 for op in ops if op.future.done() and op.future.exception() is None)
    return succeeded

def sync_append_file(reactor, filename, content, flush=False, safe_write=False, timeout=None):
    listener = setup_bg_file_operations()
    op = FileOperation("append", filename, content, flush, sync=True, timeout=timeout or DEFAULT_SYNC_TIMEOUT, safe_write=safe_write)

    try:
        listener.handler.bg_queue.put(op, timeout=1.0)
    except queue.Full:
        raise FileOperationException("File operation queue is full")

    deadline = reactor.monotonic() + (timeout or DEFAULT_SYNC_TIMEOUT)

    while not op.future.done():
        if reactor.monotonic() > deadline:
            raise FileOperationTimeout("File operation timed out")

        reactor.pause(reactor.monotonic() + 0.01)
    return op.future.result()
