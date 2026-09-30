"""Read-only hook discovery through Codex's app-server protocol.

Starting the server can initialize Codex state; this module never grants trust.
"""
import json
import queue
import subprocess
import tempfile
import threading
import time


def list_hooks(cwd, timeout=15):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1)
        messages = queue.Queue()

        def read():
            try:
                for line in process.stdout:
                    messages.put(line)
            finally:
                messages.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def send(message):
            process.stdin.write(json.dumps(message) + '\n')
            process.stdin.flush()

        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'interlock-diagnostics', 'version': '1.0'},
                'capabilities': {'experimentalApi': True}}})
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Codex hook discovery timed out')
                try:
                    line = messages.get(timeout=remaining)
                except queue.Empty:
                    raise RuntimeError('Codex hook discovery timed out')
                if line is None:
                    raise RuntimeError('Codex app server exited before returning hook status; check Codex state-directory permissions')
                message = json.loads(line)
                if message.get('id') not in (1, 2):
                    continue
                if 'error' in message:
                    raise RuntimeError('Codex rejected hook discovery; check version and configuration')
                if message['id'] == 1:
                    send({'method': 'initialized', 'params': {}})
                    send({'id': 2, 'method': 'hooks/list', 'params': {'cwds': [str(cwd)]}})
                else:
                    return message['result']['data']
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()


def summarize(entries):
    """Return a conservative activation verdict, not a claim of enforcement."""
    hooks = [hook for entry in entries for hook in entry.get('hooks', [])
             if hook.get('eventName') == 'preToolUse'
             and 'interlock-codex' in hook.get('command', '')]
    errors = any(entry.get('errors') for entry in entries)
    if errors:
        return 2, 'UNKNOWN: Codex reported hook loading errors.', hooks
    if not hooks:
        return 1, 'INACTIVE: Codex did not discover an Agent Overwatch PreToolUse hook.', hooks
    if not any(h.get('enabled') and h.get('trustStatus') in ('trusted', 'managed') for h in hooks):
        return 1, 'INACTIVE: Agent Overwatch hooks are disabled or not trusted. Review /hooks in Codex CLI.', hooks
    return 0, 'READY: Codex reports an enabled, trusted hook. Run the live smoke test to verify enforcement.', hooks
