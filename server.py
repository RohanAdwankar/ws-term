#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["websockets"]
# ///
import argparse, asyncio, json, os, signal, sys, termios, tty
import websockets


class OSCStrip:
    def __init__(self):
        self.s = 0

    def feed(self, data):
        out = bytearray()
        for b in data:
            if self.s == 0:
                if b == 0x1b: self.s = 1
                else: out.append(b)
            elif self.s == 1:
                if b in (0x5d, 0x50, 0x5f, 0x5e): self.s = 2
                elif b == 0x1b: out.append(0x1b)
                else: out += bytes((0x1b, b)); self.s = 0
            elif self.s == 2:
                if b == 0x07: self.s = 0
                elif b == 0x1b: self.s = 3
            else:
                self.s = 0 if b == 0x5c else 2
        return bytes(out)


async def handle(ws, token, sanitize, state):
    path = ws.request.path
    tok = path.split("token=", 1)[1].split("&", 1)[0] if "token=" in path else ""
    if tok != token:
        await ws.close(4001, "bad token")
        print("\r\n[server] rejected (bad token)\r", file=sys.stderr)
        return
    if state["busy"]:
        await ws.close(4002, "busy")
        return
    state["busy"] = True
    loop, fd = asyncio.get_running_loop(), sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    strip = OSCStrip() if sanitize else None

    def size():
        c, r = os.get_terminal_size(sys.stdout.fileno())
        asyncio.ensure_future(ws.send(json.dumps({"type": "resize", "rows": r, "cols": c})))

    def on_in():
        d = os.read(fd, 65536)
        if d:
            asyncio.ensure_future(ws.send(d))

    loop.add_reader(fd, on_in)
    try:
        loop.add_signal_handler(signal.SIGWINCH, size)
    except (NotImplementedError, ValueError):
        pass
    size()
    print("\r\n[server] agent connected — driving the remote shell\r\n", file=sys.stderr)
    try:
        async for m in ws:
            if isinstance(m, bytes):
                os.write(sys.stdout.fileno(), strip.feed(m) if strip else m)
    except websockets.ConnectionClosed:
        pass
    finally:
        loop.remove_reader(fd)
        try:
            loop.remove_signal_handler(signal.SIGWINCH)
        except (NotImplementedError, ValueError):
            pass
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        state["busy"] = False
        print("\r\n[server] agent disconnected\r", file=sys.stderr)


async def main_async(host, port, token, sanitize):
    state = {"busy": False}
    async with websockets.serve(lambda ws: handle(ws, token, sanitize, state),
                                host, port, max_size=None, ping_interval=20):
        print(f"[server] listening ws://{host}:{port}; expose it (ngrok http {port}) "
              "and point the agent at the wss:// url", file=sys.stderr)
        await asyncio.Future()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default=os.environ.get("WSTERM_TOKEN", ""))
    p.add_argument("--raw", action="store_true")
    a = p.parse_args()
    if not a.token:
        p.error("no token (pass --token or WSTERM_TOKEN); it pipes to a shell")
    try:
        asyncio.run(main_async(a.host, a.port, a.token, not a.raw))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
