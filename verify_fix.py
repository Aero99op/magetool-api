import requests
import os
from pathlib import Path

# Local API URL
API_URL = "http://localhost:8000"

def test_extension_fix():
    print("🚀 Starting File Extension Fix Verification...")
    
    # 1. Create a dummy file WITHOUT extension in temp dir
    # We need to find where temp dir is. Assume ./temp for now or read from env
    temp_dir = Path("d:/NLP exps/magetool-api/temp")
    temp_dir.mkdir(exist_ok=True)
    
    # Create a dummy MP4 file (using minimal header)
    test_filename = "test-video-no-ext"
    test_file_path = temp_dir / test_filename
    
    # Minimal MP4 header (ftypisom)
    mp4_header = b'\x00\x00\x00\x18ftypisom\x00\x00\x02\x00mp41iso2avc1'
    with open(test_file_path, 'wb') as f:
        f.write(mp4_header + b'\x00' * 1024)
        
    print(f"✅ Created dummy file: {test_file_path}")
    
    try:
        # 2. Request download
        download_url = f"{API_URL}/api/download/{test_filename}"
        print(f"📥 Requesting download: {download_url}")
        
        response = requests.get(download_url)
        
        if response.status_code != 200:
            print(f"❌ Failed to download: Status {response.status_code}")
            return
            
        # 3. Check Content-Disposition header
        cd_header = response.headers.get("Content-Disposition", "")
        print(f"📋 Content-Disposition: {cd_header}")
        
        if 'filename="test-video-no-ext.mp4"' in cd_header:
            print("✅ SUCCESS: Server appended .mp4 extension in header!")
        else:
            print("❌ FAILURE: Extension not found in header.")
            
        # 4. Check if file was renamed on disk
        expected_renamed_path = temp_dir / f"{test_filename}.mp4"
        if expected_renamed_path.exists():
             print(f"✅ SUCCESS: File was renamed on disk to {expected_renamed_path.name}")
        else:
             print(f"⚠️ NOTICE: File was NOT renamed on disk (might be intended behavior or race condition)")
             
        # Cleanup
        if expected_renamed_path.exists():
            os.remove(expected_renamed_path)
        if test_file_path.exists():
            os.remove(test_file_path)
            
    except Exception as e:
        print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    test_extension_fix()
