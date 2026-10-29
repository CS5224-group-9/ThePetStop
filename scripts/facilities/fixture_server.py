"""Deterministic AVS PDFs and OneMap responses for isolated ingestion checks."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROWS = {
    "vet": [
        ["1", "FIXTURE VET A", "1", "FIXTURE ROAD", "NIL", "01", "01", "080001"],
        ["2", "FIXTURE VET B", "2", "FIXTURE ROAD", "NIL", "01", "02", "080002"],
    ],
    "pet_shop": [
        [
            "AB123456",
            "FIXTURE SHOP A",
            "3",
            "FIXTURE ROAD",
            "#01",
            "03",
            "NIL",
            "080003",
            "*",
            "*",
            "",
            "",
            "",
            "",
        ],
        [
            "AB123457",
            "FIXTURE SHOP B",
            "4",
            "FIXTURE ROAD",
            "#01",
            "04",
            "NIL",
            "080004",
            "",
            "",
            "*",
            "*",
            "*",
            "*",
        ],
    ],
}
SCENARIO = {"name": "happy", "requests": 0}


def pdf(source):
    header = ["No", "Name", "Block", "Street", "Building", "Floor", "Unit", "Postal"]
    if source == "pet_shop":
        header += ["D", "C", "SM", "B", "MF", "F"]
    rows = [
        header,
        *ROWS[source],
    ]
    drawing = []
    column_width = 100
    for col in range(len(header) + 1):
        x = 20 + col * column_width
        drawing.append(f"{x} 450 m {x} 540 l S")
    for row in range(4):
        y = 540 - row * 30
        drawing.append(f"20 {y} m {20 + len(header) * column_width} {y} l S")
    for row_no, row in enumerate(rows):
        for col, value in enumerate(row):
            drawing.append(
                f"BT /F1 7 Tf {23 + col * column_width} {521 - row_no * 30} Td ({value}) Tj ET"
            )
    stream = "\n".join(drawing).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {50 + len(header) * column_width} 600] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    result = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(result)
    result += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    result += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    return result


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, content, kind="application/json", headers=None):
        body = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/scenario":
            value = json.loads(
                self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 1000))
            )
            if value.get("name") not in {"happy", "malformed", "throttle", "expired"}:
                self.respond(400, {})
                return
            SCENARIO.update(name=value["name"], requests=0)
            self.respond(200, SCENARIO)
        else:
            self.respond(
                200,
                {
                    "access_token": "fixture-valid",
                    "expiry_timestamp": int(time.time()) + 3600,
                },
            )

    def do_GET(self):
        parsed = urlparse(self.path)
        source = parsed.path.split("/")[1]
        if parsed.path == "/health":
            self.respond(200, {"healthy": True})
        elif source in ROWS and parsed.path.endswith("/registry"):
            self.respond(
                200,
                f'<a href="/{source}/registry file.pdf">{source} veterinary pet shop PDF</a>'.encode(),
                "text/html",
            )
        elif source in ROWS and parsed.path.endswith(".pdf"):
            self.respond(
                200,
                b"%PDF-invalid" if SCENARIO["name"] == "malformed" else pdf(source),
                "application/pdf",
            )
        elif parsed.path.endswith("/search"):
            SCENARIO["requests"] += 1
            if SCENARIO["name"] == "throttle" and SCENARIO["requests"] == 1:
                self.respond(429, {}, headers={"Retry-After": "1"})
            elif self.headers.get("Authorization") == "fixture-expired":
                self.respond(401, {})
            else:
                postal = parse_qs(parsed.query).get("searchVal", [""])[0]
                self.respond(
                    200,
                    {
                        "results": [
                            {"POSTAL": postal, "LATITUDE": "1.3", "LONGITUDE": "103.8"}
                        ]
                    },
                )
        else:
            self.respond(404, {})

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
