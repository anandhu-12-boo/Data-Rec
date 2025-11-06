import os
from pathlib import Path
from flask import Flask, render_template, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['THUMB_FOLDER'] = os.path.join('static', 'thumbs')

socketio = SocketIO(app, cors_allowed_origins="*")

os.makedirs(app.config['THUMB_FOLDER'], exist_ok=True)

scan_thread = None
stop_event = threading.Event()

# Global scan statistics
scan_stats = {
    'total_files': 0,
    'processed_files': 0,
    'total_images': 0,
    'current_file': '',
    'current_file_images': 0
}

# ---------------------------
# 1️⃣ Get Windows Username
# ---------------------------
def get_windows_username():
    try:
        return os.getlogin()
    except Exception:
        return os.environ.get("USERNAME", "unknown")

# ---------------------------
# 2️⃣ Locate Thumbcache Files
# ---------------------------
def get_thumbcache_files():
    username = get_windows_username()
    explorer_path = Path(f"C:/Users/{username}/AppData/Local/Microsoft/Windows/Explorer")
    if not explorer_path.exists():
        raise FileNotFoundError("Explorer thumbnail cache folder not found.")
    return list(explorer_path.glob("thumbcache_*.db"))

# ---------------------------
# 3️⃣ Extract Thumbnails (with Progress)
# ---------------------------
def extract_thumbnails():
    global scan_stats
    dest_folder = Path(app.config['THUMB_FOLDER'])
    dest_folder.mkdir(parents=True, exist_ok=True)

    # Clear old images
    for old in dest_folder.glob("*"):
        try:
            old.unlink()
        except:
            pass

    thumb_files = get_thumbcache_files()
    saved_files = []

    scan_stats = {
        'total_files': len(thumb_files),
        'processed_files': 0,
        'total_images': 0,
        'current_file': '',
        'current_file_images': 0
    }

    print(f"🔍 Found {scan_stats['total_files']} thumbcache files to scan...\n")

    for file_index, thumb_file in enumerate(thumb_files, start=1):
        if stop_event.is_set():
            print("🛑 Scan stopped by user.")
            socketio.emit('scan_stopped', {
                'progress': int((file_index / scan_stats['total_files']) * 100),
                'stats': scan_stats
            })
            return saved_files

        scan_stats['current_file'] = thumb_file.name
        scan_stats['current_file_images'] = 0
        scan_stats['processed_files'] = file_index - 1

        print(f"[{file_index}/{scan_stats['total_files']}] Processing: {thumb_file.name}")

        # 🔹 Emit progress start for current file
        socketio.emit('scan_progress', {
            'progress': int(((file_index - 1) / scan_stats['total_files']) * 100),
            'message': f"Processing {thumb_file.name}...",
            'current': thumb_file.name,
            'stats': scan_stats.copy()
        })

        count = 0
        with open(thumb_file, "rb") as f:
            data = f.read()

        pos = 0
        index = 0
        while True:
            if stop_event.is_set():
                break

            start = data.find(b"\xFF\xD8\xFF", pos)
            if start == -1:
                break
            end = data.find(b"\xFF\xD9", start)
            if end == -1:
                break

            img_data = data[start:end + 2]
            img_path = dest_folder / f"{thumb_file.stem}_{index}.jpg"
            with open(img_path, "wb") as img_file:
                img_file.write(img_data)
            saved_files.append(img_path.name)

            count += 1
            scan_stats['total_images'] += 1
            scan_stats['current_file_images'] = count
            index += 1
            pos = end + 2

            # Emit progress incrementally (every ~20 images)
            if count % 20 == 0:
                socketio.emit('scan_progress', {
                    'progress': int((file_index / scan_stats['total_files']) * 100),
                    'message': f"Extracting from {thumb_file.name}...",
                    'current': thumb_file.name,
                    'stats': scan_stats.copy()
                })

        print(f"   → Extracted {count} images from {thumb_file.name} (Total: {scan_stats['total_images']})")

        scan_stats['processed_files'] = file_index
        socketio.emit('file_processed', {
            'filename': thumb_file.name,
            'count': count,
            'stats': scan_stats.copy()
        })

        # 🔹 Emit after finishing this file
        socketio.emit('scan_progress', {
            'progress': int((file_index / scan_stats['total_files']) * 100),
            'message': f"Completed {thumb_file.name}",
            'current': thumb_file.name,
            'stats': scan_stats.copy()
        })

        time.sleep(0.3)

    print(f"\n✅ Scan complete — {scan_stats['total_images']} images extracted.\n")

    # 🔹 Final progress update
    socketio.emit('scan_progress', {
        'progress': 100,
        'message': 'Scan completed!',
        'current': '',
        'stats': scan_stats.copy()
    })

    socketio.emit('scan_complete', {
        'progress': 100,
        'files': saved_files,
        'stats': scan_stats.copy()
    })
    socketio.emit('refresh_thumbs')
    return saved_files

# ---------------------------
# 4️⃣ Background Thread
# ---------------------------
def scan_thread_fn():
    stop_event.clear()
    extract_thumbnails()

# ---------------------------
# 5️⃣ Routes
# ---------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/thumbs/<path:filename>')
def send_thumb(filename):
    return send_from_directory(app.config['THUMB_FOLDER'], filename)

@app.route('/thumbs-list')
def thumbs_list():
    thumbs = [f for f in os.listdir(app.config['THUMB_FOLDER']) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    return jsonify(sorted(thumbs))

@app.route('/scan-stats')
def get_scan_stats():
    return jsonify(scan_stats)

# ---------------------------
# 6️⃣ Socket.IO Events
# ---------------------------
@socketio.on('start_scan')
def start_scan():
    global scan_thread
    thumb_folder = Path(app.config['THUMB_FOLDER'])
    if thumb_folder.exists():
        for old_file in thumb_folder.glob("*"):
            try:
                old_file.unlink()
            except Exception as e:
                print(f"⚠️ Could not delete {old_file}: {e}")
        print("🧹 Cleared old thumbnails before starting new scan.")
        emit('scan_progress', {
    'progress': 0,
    'message': '🧹 Cleared old thumbnails, starting new scan...',
    'current': '',
    'stats': scan_stats.copy()
})


    if scan_thread and scan_thread.is_alive():
        emit('scan_progress', {
    'progress': 0,
    'message': '⚠️ Scan already running...',
    'current': '',
    'stats': scan_stats.copy()
})
        return

    scan_thread = threading.Thread(target=scan_thread_fn)
    scan_thread.start()
    print("✅ Started new scan thread.")

@socketio.on('stop_scan')
def stop_scan():
    stop_event.set()
    emit('scan_stopped', {'progress': 0, 'stats': scan_stats})

@socketio.on('get_stats')
def send_stats():
    emit('current_stats', {'stats': scan_stats})

# ---------------------------
# 7️⃣ Run
# ---------------------------
if __name__ == '__main__':
    print("✅ FileRescue server running at http://localhost:5000")
    socketio.run(app, debug=True, port=5000, use_reloader=False)
