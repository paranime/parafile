"""
Parafile — a local file ledger.
Run:  pip install flask
      python app.py
"""

import os

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
import shutil

def get_free_storage(path='/'):
    """
    Return free storage space in bytes on the filesystem containing `path`.
    Raises OSError if the path is invalid or inaccessible.
    """
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except OSError as e:
        raise RuntimeError(f"Failed to get disk usage: {e}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# SOFT_CAP = 512 * 1024 * 1024  # storage meter ceiling (display only)
SOFT_CAP = free_bytes = get_free_storage('/')          # root filesystem

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024  # hard upload limit


def unique_name(filename: str) -> str:
    """Avoid clobbering: append -1, -2, ... if the name already exists."""
    base, ext = os.path.splitext(filename)
    candidate, n = filename, 1
    while os.path.exists(os.path.join(UPLOAD_DIR, candidate)):
        candidate = f"{base}-{n}{ext}"
        n += 1
    return candidate


def safe_path(name: str) -> str:
    """Reject anything that is not a plain filename (no paths, no traversal)."""
    if os.path.basename(name) != name or name in {".", ".."}:
        abort(400)
    return os.path.join(UPLOAD_DIR, name)


def serialize(name: str) -> dict:
    st = os.stat(os.path.join(UPLOAD_DIR, name))
    ext = os.path.splitext(name)[1].lstrip(".").upper()
    return {"name": name, "ext": ext or "FILE", "size": st.st_size, "modified": st.st_mtime}


def dir_size() -> int:
    return sum(
        os.path.getsize(os.path.join(UPLOAD_DIR, f))
        for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/files")
def list_files():
    files = [
        serialize(f)
        for f in sorted(os.listdir(UPLOAD_DIR))
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    ]
    return jsonify(files=files, total=dir_size(), cap=SOFT_CAP)


@app.route("/api/upload", methods=["POST"])
def upload():
    blobs = [f for f in request.files.getlist("files") if f.filename]
    if not blobs:
        return jsonify(error="No files received"), 400
    saved = []
    for blob in blobs:
        name = unique_name(os.path.basename(blob.filename))
        blob.save(os.path.join(UPLOAD_DIR, name))
        saved.append(serialize(name))
    return jsonify(saved=saved, total=dir_size(), cap=SOFT_CAP), 201


@app.route("/api/files/<name>/download")
def download(name):
    safe_path(name)  # validate before serving
    return send_from_directory(UPLOAD_DIR, name, as_attachment=True)


@app.route("/api/files/<name>", methods=["DELETE"])
def delete(name):
    path = safe_path(name)
    if not os.path.isfile(path):
        return jsonify(error="File not found"), 404
    os.remove(path)
    return jsonify(deleted=name, total=dir_size(), cap=SOFT_CAP)


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Upload exceeds the 256 MB limit"), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    