import os
import shutil
import subprocess
import json
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist")
BUILD_DIR = os.path.join(ROOT, "build")
RELEASE_DIR = os.path.join(DIST_DIR, "SRT-Translator_Release")
ZIP_OUT = r"C:\Users\admin12\Downloads\SRT-Translator.zip"

def main():
    print("=== STARTING BUILD PROCESS ===")

    # 1. Build using PyInstaller
    print("\n[1/5] Building Executable with PyInstaller...")
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        f"--icon={os.path.join(ROOT, 'assets', 'icon.ico')}",
        f"--add-data=assets{os.pathsep}assets",
        "--name=SRT-Translator",
        os.path.join(ROOT, "app.py")
    ]
    
    print("Running command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        print("[ERROR] PYINSTALLER BUILD FAILED!")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        return
    print("[OK] PyInstaller build completed successfully!")

    # 2. Create Release Folder
    print("\n[2/5] Creating release structure...")
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR)
    os.makedirs(RELEASE_DIR, exist_ok=True)

    # 3. Copy Executable
    exe_src = os.path.join(DIST_DIR, "SRT-Translator.exe")
    exe_dst = os.path.join(RELEASE_DIR, "SRT-Translator.exe")
    print(f"Copying {exe_src} -> {exe_dst}")
    shutil.copy2(exe_src, exe_dst)

    # 4. Create Clean config.json (NO API keys)
    cfg_dst = os.path.join(RELEASE_DIR, "config.json")
    print(f"Creating clean config -> {cfg_dst}")
    clean_config = {
        "api_keys": [],  # Clean API keys
        "model": "deepseek-v4-flash",
        "target_language": "indonesian",
        "content_type": "auto",
        "batch_size": 60,
        "output_subfolder": True,
        "glossary": {}
    }
    with open(cfg_dst, "w", encoding="utf-8") as f:
        json.dump(clean_config, f, indent=2, ensure_ascii=False)

    # Also copy assets folder just in case user wants raw assets
    assets_dst = os.path.join(RELEASE_DIR, "assets")
    shutil.copytree(os.path.join(ROOT, "assets"), assets_dst, dirs_exist_ok=True)

    # 5. Create ZIP archive
    print(f"\n[3/5] Zipping output to {ZIP_OUT}...")
    if os.path.exists(ZIP_OUT):
        os.remove(ZIP_OUT)
        
    with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                # Keep path relative to RELEASE_DIR so it extracts nicely into a folder
                arc_name = os.path.relpath(file_path, DIST_DIR)
                zipf.write(file_path, arcname=arc_name)
    print("[OK] ZIP created successfully!")

    # 6. Cleanup build artifacts
    print("\n[4/5] Cleaning up temporary build files...")
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    shutil.rmtree(RELEASE_DIR, ignore_errors=True)
    spec_file = os.path.join(ROOT, "SRT-Translator.spec")
    if os.path.exists(spec_file):
        os.remove(spec_file)
    print("[OK] Cleanup complete!")

    print(f"\n[SUCCESS] ALL DONE! Your release zip is ready at: {ZIP_OUT}")

if __name__ == "__main__":
    main()
