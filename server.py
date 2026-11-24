import json
import os
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

PORT = 8080
BOT_TOKEN = "local_bot_token"

updates_queue = []
messages_history = []
update_counter = 1
message_counter = 1
lock = threading.Lock()


class LocalBotAPIHandler(SimpleHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith(f"/bot{BOT_TOKEN}/getUpdates"):
            params = parse_qs(parsed.query)
            offset = int(params.get("offset", [0])[0])

            with lock:
                result = [u for u in updates_queue if u["update_id"] >= offset]

            self._send_json({"ok": True, "result": result})
            return

        if parsed.path == "/api/messages":
            with lock:
                history = list(messages_history)
            self._send_json({"ok": True, "messages": history})
            return

        if parsed.path in ("/", ""):
            self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        global update_counter, message_counter
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except json.JSONDecodeError:
            payload = {}

        if parsed.path == "/api/send":
            text = payload.get("text", "").strip()
            chat_id = payload.get("chat_id", 1001)

            if not text:
                self._send_json({"ok": False, "description": "Empty text"}, 400)
                return

            with lock:
                msg_obj = {
                    "message_id": message_counter,
                    "from": {"id": chat_id, "first_name": "User", "is_bot": False},
                    "chat": {"id": chat_id, "type": "private"},
                    "date": int(time.time()),
                    "text": text,
                }
                messages_history.append(msg_obj)

                update_obj = {
                    "update_id": update_counter,
                    "message": msg_obj,
                }
                updates_queue.append(update_obj)

                message_counter += 1
                update_counter += 1

            self._send_json({"ok": True, "result": msg_obj})
            return

        if parsed.path.startswith(f"/bot{BOT_TOKEN}/sendMessage"):
            chat_id = payload.get("chat_id", 1001)
            text = payload.get("text", "")

            with lock:
                msg_obj = {
                    "message_id": message_counter,
                    "from": {"id": 1, "first_name": "EchoBot", "is_bot": True},
                    "chat": {"id": chat_id, "type": "private"},
                    "date": int(time.time()),
                    "text": text,
                }
                messages_history.append(msg_obj)
                message_counter += 1

            self._send_json({"ok": True, "result": msg_obj})
            return

        self._send_json({"ok": False, "description": "Not Found"}, 404)


def run_echo_bot():
    time.sleep(1)
    offset = 0
    base_url = f"http://127.0.0.1:{PORT}/bot{BOT_TOKEN}"

    while True:
        try:
            get_req = Request(f"{base_url}/getUpdates?offset={offset}")
            with urlopen(get_req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))

            for update in payload.get("result", []):
                offset = max(offset, update["update_id"] + 1)
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "")

                if chat_id and text:
                    reply_payload = json.dumps(
                        {"chat_id": chat_id, "text": f"Эхо: {text}"}
                    ).encode("utf-8")
                    send_req = Request(
                        f"{base_url}/sendMessage",
                        data=reply_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(send_req, timeout=5):
                        pass

        except Exception:
            pass
        time.sleep(0.5)


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_echo_bot, daemon=True)
    bot_thread.start()

    server = HTTPServer(("0.0.0.0", PORT), LocalBotAPIHandler)
    print(f"Сервер запущен на http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
        server.server_close()
