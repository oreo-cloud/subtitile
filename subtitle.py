"""
影片字幕自動生成工具 (無 Argparse 版)

使用 whisper.cpp 為影片自動生成繁體中文字幕
- 直接在程式碼開頭修改設定
- 自動轉碼音訊為 16kHz/16-bit
- 跨平台支援 (Windows/macOS/Linux)
"""

import subprocess
import os
import sys
import shutil
import platform
from pathlib import Path
from typing import List, Optional

# ==========================================
# 👇 【使用者設定區域】請在此修改設定
# ==========================================

# 輸入影片的資料夾
INPUT_DIR = 'video'

# 輸出字幕的資料夾
OUTPUT_DIR = 'subtitle'

# 模型檔案路徑 (例如: ggml-large-v3.bin)
MODEL_PATH = 'ggml-large-v3.bin'

# whisper.cpp 的執行檔名稱 (Windows 通常是 main.exe，Mac/Linux 是 main)
# 如果執行檔不在同目錄，請填寫完整路徑
WHISPER_EXEC_NAME = 'main'

# 支援的影片格式
SUPPORTED_EXTENSIONS = {'.mp4', '.mov', '.m4a', '.mp3', '.mkv', '.wav', '.webm', '.flv'}

PROMPT_TEXT = '以下內容為資訊工程學系「資料結構與演算法」課程的上課錄影逐字稿，使用繁體中文。課程以中文授課，但遇到專有名詞、資料結構、演算法名稱與技術術語時請保留英文原文，不要音譯或自行翻譯，並正確轉寫。'

# ==========================================
# 👆 設定結束
# ==========================================

# 嘗試導入 tqdm
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# 全域變數用來儲存確認過的執行檔路徑
VALID_WHISPER_PATH = ""

def check_dependencies() -> Optional[str]:
    """
    檢查必要的依賴是否存在
    Returns: None if success, error message string if failed
    """
    global VALID_WHISPER_PATH

    # 1. 檢查 ffmpeg
    if not shutil.which('ffmpeg'):
        return "❌ 找不到 ffmpeg，請確保已安裝並加入系統環境變數 PATH 中。"
    
    # 2. 檢查 whisper.cpp 執行檔
    target_exec = WHISPER_EXEC_NAME
    
    # Windows 自動補全 .exe (如果使用者沒寫)
    if platform.system() == "Windows" and not target_exec.lower().endswith('.exe'):
        candidates = [f"{target_exec}.exe", target_exec]
    else:
        candidates = [target_exec]

    found_exec = None
    # 先找系統路徑，再找當前路徑
    for cand in candidates:
        if shutil.which(cand):
            found_exec = shutil.which(cand)
            break
        if Path(cand).resolve().is_file():
            found_exec = str(Path(cand).resolve())
            break
            
    if not found_exec:
        return f"❌ 找不到 whisper.cpp 執行檔: {WHISPER_EXEC_NAME}"
    
    VALID_WHISPER_PATH = found_exec

    # 3. 檢查模型檔案
    if not Path(MODEL_PATH).is_file():
        return f"❌ 找不到模型檔案: {MODEL_PATH}"
    
    return None

def extract_audio(input_file: Path, output_wav: Path) -> bool:
    """使用 ffmpeg 提取並優化音頻"""
    cmd = [
        'ffmpeg', '-y', 
        '-v', 'error',         # 減少輸出訊息
        '-i', str(input_file),
        '-ar', '16000',        # 採樣率
        '-ac', '1',            # 單聲道
        '-c:a', 'pcm_s16le',   # 16-bit
        '-af', 'loudnorm,highpass=f=80,lowpass=f=8000', # 濾鏡
        str(output_wav)
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ FFmpeg 錯誤: {e.stderr.decode('utf-8', errors='ignore')}")
        return False

def run_whisper(wav_file: Path) -> bool:
    """執行 whisper.cpp 生成字幕"""
    cmd = [
        VALID_WHISPER_PATH,
        '-m', MODEL_PATH,
        '-f', str(wav_file),
        '-l', 'zh',            
        '--prompt', PROMPT_TEXT, 
        '-osrt'                
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # 檢查是否生成了預期的 .srt 檔案 (whisper.cpp 預設行為: input.wav -> input.wav.srt)
        expected_srt = wav_file.with_suffix(wav_file.suffix + '.srt')
        if expected_srt.exists():
            return True
        return False
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Whisper 錯誤: {e.stderr.decode('utf-8', errors='ignore')}")
        return False

def process_single_file(video_path: Path, input_root: Path, output_root: Path) -> bool:
    """處理單個檔案的完整流程"""
    # 計算相對路徑
    try:
        rel_path = video_path.relative_to(input_root)
    except ValueError:
        rel_path = video_path.name
        
    target_srt_path = output_root / rel_path.parent / f"{video_path.stem}.srt"
    
    # 檢查是否已存在
    if target_srt_path.exists():
        return False 
        
    # 建立輸出目錄
    target_srt_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 臨時 WAV 路徑 (放在輸出目錄，處理完刪除)
    temp_wav = target_srt_path.parent / f"{video_path.stem}_temp.wav"
    temp_srt_generated = temp_wav.with_suffix('.wav.srt') 
    
    result = False
    try:
        # 1. 提取音頻
        if extract_audio(video_path, temp_wav):
            # 2. 生成字幕
            if run_whisper(temp_wav):
                # 3. 移動並重新命名
                if temp_srt_generated.exists():
                    shutil.move(str(temp_srt_generated), str(target_srt_path))
                    result = True
                else:
                    print(f"  ❌ 未找到生成的字幕檔")
    except Exception as e:
        print(f"  ❌ 處理異常: {e}")
    finally:
        # 清理臨時檔案
        for temp in [temp_wav, temp_srt_generated]:
            if temp.exists():
                try: os.remove(temp)
                except: pass

    return result

def main():
    print("=" * 60)
    print("🎬 影片字幕自動生成工具 (Whisper.cpp)")
    print("=" * 60)

    # 檢查依賴
    error_msg = check_dependencies()
    if error_msg:
        print(f"\n{error_msg}")
        if not TQDM_AVAILABLE:
            print("💡 提示: pip install tqdm 可獲得進度條顯示")
        sys.exit(1)

    input_root = Path(INPUT_DIR)
    output_root = Path(OUTPUT_DIR)

    if not input_root.exists():
        print(f"❌ 錯誤: 輸入目錄不存在 '{input_root}'")
        sys.exit(1)

    # 掃描檔案
    print("\n🔍 正在掃描影片檔案...")
    tasks = []
    for root, _, files in os.walk(input_root):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                # 檢查是否已存在字幕
                rel_p = file_path.relative_to(input_root)
                dest_srt = output_root / rel_p.parent / f"{file_path.stem}.srt"
                if not dest_srt.exists():
                    tasks.append(file_path)

    total_tasks = len(tasks)
    if total_tasks == 0:
        print("✅ 沒有需要處理的影片 (可能都已生成字幕)。")
        return

    print(f"📊 待處理影片數: {total_tasks}\n")

    success_count = 0
    fail_count = 0

    # 進度條處理
    iterator = tqdm(tasks, unit="片", ncols=80) if TQDM_AVAILABLE else tasks
    
    for video_file in iterator:
        rel_name = video_file.relative_to(input_root)
        
        if not TQDM_AVAILABLE:
            print(f"正在處理: {rel_name} ...", end="", flush=True)

        is_success = process_single_file(video_file, input_root, output_root)
        
        if is_success:
            success_count += 1
            if not TQDM_AVAILABLE: print(" ✅ 完成")
        else:
            fail_count += 1
            if not TQDM_AVAILABLE: print(" ❌ 失敗")

    print("\n" + "=" * 60)
    print(f"🏁 處理完成")
    print(f"✅ 成功: {success_count} | ❌ 失敗: {fail_count}")
    print(f"📂 字幕位置: {output_root.absolute()}")
    print("=" * 60)

if __name__ == "__main__":
    main()