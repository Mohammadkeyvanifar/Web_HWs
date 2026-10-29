import os
import socket
import threading
import urllib.request

HOST = "0.0.0.0"
PORT = 8888
PUBLIC_DIR = r"D:\دانشگاه\term 7\برنامه نویسی وب\HW2\http-server\public"
UPSTREAM = "http://127.0.0.1:9000"  # سرور دوم برای /api

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".ico": "image/x-icon",
}


def build_response(status, reason, body=b"", content_type="text/plain; charset=utf-8", extra_headers=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    if extra_headers:
        headers.extend(extra_headers)
    head = "\r\n".join(headers) + "\r\n\r\n"
    return head.encode("utf-8") + body


def parse_request(raw):
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    if not lines or not lines[0]:
        raise ValueError("empty request")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise ValueError("bad request line")
    method, path, version = parts
    headers = {}
    for line in lines[1:]:
        if line == "":
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    return method, path, version, headers


def safe_path(url_path):
    # حذف query string
    path = url_path.split("?", 1)[0]
    if path == "/":
        path = "/index.html"
    # جلوگیری از path traversal
    full = os.path.normpath(os.path.join(PUBLIC_DIR, path.lstrip("/")))
    if not full.startswith(PUBLIC_DIR + os.sep) and full != PUBLIC_DIR:
        return None
    return full


def serve_file(path):
    if not os.path.isfile(path):
        return build_response(404, "Not Found", "404 Not Found")
    ext = os.path.splitext(path)[1].lower()
    ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        data = f.read()
    return build_response(200, "OK", data, ctype)


def proxy(path, headers, method):
    url = UPSTREAM + path
    req = urllib.request.Request(url, method=method)
    for k in ("accept", "user-agent", "content-type"):
        if k in headers:
            req.add_header(k, headers[k])
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "application/octet-stream")
            return build_response(resp.status, resp.reason, body, ctype)
    except Exception:
        return build_response(502, "Bad Gateway", "502 Bad Gateway")


def handle_client(conn):
    try:
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk
        if not raw:
            return
        method, path, version, headers = parse_request(raw)

        if method not in ("GET", "HEAD"):
            conn.sendall(build_response(405, "Method Not Allowed", "405 Method Not Allowed"))
            return

        if path.startswith("/api"):
            response = proxy(path, headers, method)
        else:
            full = safe_path(path)
            if full is None:
                response = build_response(403, "Forbidden", "403 Forbidden")
            else:
                response = serve_file(full)

        if method == "HEAD":
            head, _, _ = response.partition(b"\r\n\r\n")
            conn.sendall(head + b"\r\n\r\n")
        else:
            conn.sendall(response)
    except ValueError:
        try:
            conn.sendall(build_response(400, "Bad Request", "400 Bad Request"))
        except Exception:
            pass
    except Exception:
        try:
            conn.sendall(build_response(500, "Internal Server Error", "500 Internal Server Error"))
        except Exception:
            pass
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    print(f"Server running on http://{HOST}:{PORT}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()