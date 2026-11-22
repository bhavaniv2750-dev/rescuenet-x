"""Black-box check that evidence photos and report identifiers are not exposed to anonymous callers.

    python scripts/probe_public_exposure.py http://127.0.0.1:8000

Uses only the standard library. It CREATES a few test reports and uploads, so run it against a development or
throw-away database, never against operational data. Exit code 1 if anything is exposed.
"""
import io
import json
import struct
import sys
import urllib.error
import urllib.request
import uuid
import zlib

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
failures = []


def call(method, path, body=None, headers=None, raw=None, ctype=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = ctype or "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def tiny_png():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes([40, 90, 160]) * 8 for _ in range(8))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def multipart(name, data):
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode() \
        + data + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


body, ctype = multipart("probe.png", tiny_png())
st, out, _ = call("POST", "/api/incidents/upload-image", raw=body, ctype=ctype)
check("guest can upload a photo", st == 201, st)
up = json.loads(out) if st == 201 else {}
report = dict(title="Probe report", description="Automated exposure probe, ignore", area="Probe", latitude=12.9, longitude=77.6,
              severity="LOW", people_affected=1, image_url=up.get("image_url"))
st, out, _ = call("POST", "/api/public/reports", report)
check("guest can report without an account", st == 201, st)
rep = json.loads(out) if st == 201 else {}

if up.get("image_url"):
    check("photo is NOT readable anonymously", call("GET", up["image_url"])[0] == 401)
    check("photo is NOT in a static folder", all(call("GET", p)[0] == 404 for p in (
        f"/uploads/{up.get('asset_id', 'x')}.jpg", f"/api/uploads/{up.get('asset_id', 'x')}.jpg", f"/static/{up.get('asset_id', 'x')}.jpg")))
check("old public photo route is closed", call("GET", "/api/incidents/uploads/anything.png")[0] in (401, 404))
check("incident list needs sign-in", call("GET", "/api/incidents/")[0] == 401)
check("incident by id needs sign-in", call("GET", "/api/incidents/INC-1045")[0] == 401)
check("internal ids are not returned to guests", "INC-" not in json.dumps(rep))
check("counter-style ids do not exist", call("GET", "/api/public/reports/INC-1045", headers={"X-Tracking-Code": "x"})[0] == 404)
if rep:
    check("tracking works with the code", call("GET", f"/api/public/reports/{rep['public_ref']}", headers={"X-Tracking-Code": rep["tracking_code"]})[0] == 200)
    a = call("GET", f"/api/public/reports/{rep['public_ref']}", headers={"X-Tracking-Code": "0000-0000-0000-0000-0000"})
    b = call("GET", "/api/public/reports/RN-0000-0000-0000", headers={"X-Tracking-Code": "0000-0000-0000-0000-0000"})
    check("wrong code and unknown reference look identical", a[0] == b[0] == 404 and a[1] == b[1])
print("\nRESULT:", "EXPOSURE FOUND" if failures else "no exposure found")
sys.exit(1 if failures else 0)
