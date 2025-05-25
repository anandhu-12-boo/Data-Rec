from flask import Flask, render_template, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
import os
import time
import shutil
from thumbcache_parser import parse_thumbcache_file
from threading import Lock, Event
from utils import get_sys_username
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['THUMBNAIL_FOLDER'] = 'static/thumbs'

name = get_sys_username()
if name:
    app.config['THUMBCACHE_DIR'] = fr'C:\Users\{name}\AppData\Local\Microsoft\Windows\Explorer'
else:
    raise ValueError("Username not found")
socketio = SocketIO(app, async_mode='eventlet')

# Global variables for scan management
thread = None
thread_lock = Lock()
stop_event = Event()
scan_active = False

def background_scan():
    
    """Background task that handles the scanning process with detailed console logging"""
    global thread, scan_active
    
    try:
        scan_active = True
        stop_event.clear()
        
        with app.app_context():
            # Delete existing thumbnails folder
            extracted_folder = app.config['THUMBNAIL_FOLDER']
            if os.path.exists(extracted_folder):
                try:
                    shutil.rmtree(extracted_folder)
                    print(f"🗑️ Deleted existing folder: {extracted_folder}")
                except Exception as e:
                    print(f"⚠️ Failed to delete {extracted_folder}: {e}")

            # Recreate the folder for fresh extraction
            os.makedirs(extracted_folder, exist_ok=True)

            # Get list of thumbcache files
            cache_files = [f for f in os.listdir(app.config['THUMBCACHE_DIR'])
                         if f.lower().startswith('thumbcache') and f.lower().endswith('.db')]
            total_files = len(cache_files)

            # Print available files to console
            print("\n" + "="*50)
            print(f"Starting new scan at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Found {total_files} thumbcache files:")
            for i, filename in enumerate(cache_files, 1):
                print(f"{i}. {filename}")
            print("="*50 + "\n")
            

            # Notify client
            socketio.emit('scan_progress', {
                'message': 'Starting scan...',
                'progress': 0,
                'total': total_files
            }, namespace='/')

            processed = 0
            for filename in cache_files:
                if stop_event.is_set():
                    print("Scan stopped by user.")
                    socketio.emit('scan_stopped', {
                        'message': 'Scan stopped by user',
                        'processed_files': processed,
                        'total_files': total_files,
                        'code':total_files,
                        'progress': int((processed/total_files)*100)
                    }, namespace='/')
                    break

                filepath = os.path.join(app.config['THUMBCACHE_DIR'], filename)

                # Print and emit processing status
                print(f"🔍 Processing {filename}...", end=' ', flush=True)
                socketio.emit('scan_progress', {
                    'message': f'Processing {filename}...',
                    'current': filename,
                    'progress': int((processed/total_files)*100),
                    'total': total_files
                }, namespace='/')

                # Process the file
                try:
                    count = parse_thumbcache_file(filepath, app.config['THUMBNAIL_FOLDER'])
                    processed += 1
                    
                    # Print and emit success
                    print(f"✅ Success! Extracted {count} thumbnails")
                    socketio.emit('file_processed', {
                        'filename': filename,
                        'count': count,
                        'progress': int((processed/total_files)*100)
                    }, namespace='/')

                except Exception as e:
                    # Print and emit failure
                    print(f"❌ Failed! Error: {str(e)}")
                    socketio.emit('file_processed', {
                        'filename': filename,
                        'count': 0,
                        'error': str(e),
                        'progress': int((processed/total_files)*100)
                    }, namespace='/')

            if not stop_event.is_set():
                # Final status
                success_count = processed
                failure_count = total_files - processed
                print("\n" + "="*50)
                print(f"Scan completed! Success: {success_count}, Failed: {failure_count}")
                print("="*50 + "\n")
                scan_active = False
                print(f"Thread cleaned up.{scan_active}")

                socketio.emit('scan_complete', {
                    'message': 'Scan completed!',
                    'total_files': total_files,
                    'success_count': success_count,
                    'failure_count': failure_count,
                    'progress': 100
                }, namespace='/')
                
                
    finally:
        with thread_lock:
            scan_active = False
            thread = None
            print(f"Thread cleaned up.{scan_active}")
            stop_event.clear()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/thumbs/<filename>')
def serve_thumb(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename)

@app.route('/thumbs-list')
def list_thumbs():
    thumbs = sorted([f for f in os.listdir(app.config['THUMBNAIL_FOLDER']) 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    return jsonify(thumbs)

@socketio.on('start_scan', namespace='/')
def handle_start_scan():
    global thread
    with thread_lock:
        if thread is None and not scan_active:
            thread = socketio.start_background_task(background_scan)
        else:
            emit('scan_error', {
                'message': 'Scan already in progress. Please wait or stop current scan.'
            }, namespace='/')

@socketio.on('stop_scan', namespace='/')
def handle_stop_scan():
    global thread, scan_active
    with thread_lock:
        if thread is not None and scan_active:
            stop_event.set()
            emit('scan_status', {
                'message': 'Stopping scan...',
                'status': 'stopping'
            }, namespace='/')

if __name__ == '__main__':
    if not os.path.exists(app.config['THUMBNAIL_FOLDER']):
        os.makedirs(app.config['THUMBNAIL_FOLDER'])
    socketio.run(app, debug=True)