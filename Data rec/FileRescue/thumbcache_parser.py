import os
import time
import shutil
from PIL import Image

def safe_delete(filepath, max_retries=3, delay=0.1):
    """Safely delete a file with retries"""
    for i in range(max_retries):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except (PermissionError, OSError):
            if i == max_retries - 1:
                return False
            time.sleep(delay)
    return False

def parse_thumbcache_file(db_path, output_dir):
    """Parse individual thumbcache file and extract thumbnails"""
    count = 0
    try:
        # Create temporary copy to avoid file locking issues
        temp_path = os.path.join(output_dir, f"temp_{os.path.basename(db_path)}")
        try:
            shutil.copy2(db_path, temp_path)
            with open(temp_path, 'rb') as f:
                data = f.read()
        finally:
            safe_delete(temp_path)

        pos = 0
        while pos < len(data):
            # Look for JPEG markers
            if pos + 4 < len(data) and data[pos:pos+2] == b'\xFF\xD8':
                end_pos = data.find(b'\xFF\xD9', pos)
                if end_pos == -1:
                    break

                jpeg_data = data[pos:end_pos+2]
                output_path = os.path.join(output_dir, f"thumb_{os.path.basename(db_path)}_{count}.jpg")
                temp_output = output_path + ".tmp"

                # Write to temporary file first
                with open(temp_output, 'wb') as img_file:
                    img_file.write(jpeg_data)

                # Validate the image
                try:
                    img = Image.open(temp_output)
                    img.verify()
                    img.close()
                    os.rename(temp_output, output_path)
                    count += 1
                    pos = end_pos + 2
                except:
                    safe_delete(temp_output)
                    pos += 2
            else:
                pos += 1

        return count
    except Exception as e:
        print(f"Error processing {db_path}: {str(e)}")
        return 0

def scan_thumbcache_directory(cache_dir, output_dir):
    """Scan directory for thumbcache files and process them"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Clear existing thumbnails
    for f in os.listdir(output_dir):
        filepath = os.path.join(output_dir, f)
        if not safe_delete(filepath):
            print(f"Warning: Could not delete {filepath}")

    total = 0
    for filename in os.listdir(cache_dir):
        if filename.lower().startswith('thumbcache') and filename.lower().endswith('.db'):
            filepath = os.path.join(cache_dir, filename)
            try:
                total += parse_thumbcache_file(filepath, output_dir)
            except Exception as e:
                print(f"Skipping {filename} due to error: {str(e)}")
    return total