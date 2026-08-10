#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["websockets"]
# ///
import argparse, asyncio, fcntl, json, os, pty, signal, struct, sys, termios
import websockets


async def run(url, token, shell):
    url += ("&" if "?" in url else "?") + "token=" + token + "&role=agent"
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.setdefault("TERM", "xterm-256color")
        os.execvp(shell, [shell])
        os._exit(127)
    loop = asyncio.get_running_loop()
    print(f"[agent] shell pid={pid}, connecting to {url.split('?')[0]} ...", file=sys.stderr)
    async with websockets.connect(url, max_size=None, ping_interval=20) as ws:
        print("[agent] connected", file=sys.stderr)
        closed = asyncio.Event()

        def on_pty():
            try:
                data = os.read(fd, 65536)
            except OSError:
                data = b""
            if not data:
                loop.remove_reader(fd)
                closed.set()
            else:
                asyncio.ensure_future(ws.send(data))

        loop.add_reader(fd, on_pty)

        async def rx():
            try:
                async for m in ws:
                    if isinstance(m, bytes):
                        os.write(fd, m)
                    else:
                        o = json.loads(m)
                        if o.get("type") == "resize":
                            fcntl.ioctl(fd, termios.TIOCSWINSZ,
                                        struct.pack("HHHH", o["rows"], o["cols"], 0, 0))
            except websockets.ConnectionClosed:
                pass

        tasks = [asyncio.ensure_future(rx()), asyncio.ensure_future(closed.wait())]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    for fn in (lambda: loop.remove_reader(fd), lambda: os.kill(pid, signal.SIGKILL),
               lambda: os.waitpid(pid, 0)):
        try:
            fn()
        except (OSError, ValueError):
            pass
    print("[agent] session ended", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("url", nargs="?", default=os.environ.get("WSTERM_URL"))
    p.add_argument("--token", default=os.environ.get("WSTERM_TOKEN", ""))
    p.add_argument("--shell", default=os.environ.get("SHELL", "/bin/bash"))
    a = p.parse_args()
    if not a.url or not a.token:
        p.error("need a url and --token (or WSTERM_URL / WSTERM_TOKEN)")
    try:
        asyncio.run(run(a.url, a.token, a.shell))
    except (KeyboardInterrupt, ConnectionError):
        pass


if __name__ == "__main__":
    main()
