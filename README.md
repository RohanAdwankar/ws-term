# wsterm — a terminal into a no-inbound VM over WebSocket

For VMs which can only make outbound connections you can still dial out to a WebSocket (eg. for the Claude mobile app).
Running `server.py` on your machine (it's the WS endpoint taking in input) and `agent.py` on the VM allows you to get a shell into the VM.

## Run

**Your laptop:**
```bash
TOKEN=$(openssl rand -hex 16); echo "$TOKEN"
uv run server.py --port 8765 --token "$TOKEN"
ngrok http 8765
```

**On the VM:**
```bash
uv run agent.py wss://XXXX.ngrok-free.app --token <TOKEN>
```

The moment it connects, your `server.py` terminal is a shell on the VM.
Quit locally with Ctrl-C.
