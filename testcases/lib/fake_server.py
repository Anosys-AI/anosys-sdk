"""
Local stand-in for the OpenAI API and AnoSys ingestion, used by the end-to-end checks.

    python3 fake_server.py <out_dir> <port>

- POST /v1/chat/completions     answers like OpenAI; the answer carries the marker
                                LEAK_ANSWER and a fake secret (sk-proj-...) that must be scrubbed
- POST /v1/messages             answers like the Anthropic API, same markers
- POST /status/<code>/<tag>     records the body, answers with HTTP <code> (retry tests)
- POST /<tag>/...  (anything)   records the body to <out_dir>/<tag>.jsonl, answers 200

Never forwards anything: it only listens on 127.0.0.1.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

ANSWER = {
    "id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": "LEAK_ANSWER key sk-proj-abcdefghijklmnopqrstuvwx"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


ANTHROPIC_ANSWER = {
    "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": "LEAK_ANSWER key sk-proj-abcdefghijklmnopqrstuvwx"}],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 5, "output_tokens": 3},
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, {"ok": True})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0) or 0))
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if self.path.startswith("/v1/chat/completions"):
            return self._reply(200, ANSWER)
        if self.path.startswith("/v1/messages"):
            return self._reply(200, ANTHROPIC_ANSWER)
        code = 200
        if parts and parts[0] == "status" and len(parts) >= 3:
            code, parts = int(parts[1]), parts[2:]
        tag = parts[0] if parts else "default"
        with open(OUT / f"{tag}.jsonl", "ab") as fh:
            fh.write(body.replace(b"\n", b" ") + b"\n")
        with open(OUT / f"{tag}.headers", "a") as fh:
            fh.write(json.dumps({"anosys-apikey": self.headers.get("anosys-apikey")}) + "\n")
        self._reply(code, {})


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), Handler).serve_forever()
