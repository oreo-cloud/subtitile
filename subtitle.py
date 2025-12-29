"""
影片字幕自動生成工具

使用 whisper.cpp 為影片自動生成繁體中文字幕
- 輸入目錄：video/
- 輸出目錄：subtitle/
- 支援格式：.mp4, .mov, .m4a, .mp3, .mkv, .wav
"""

import subprocess
import os
import sys
import shutil
from pathlib import Path
from typing import List, Tuple

# 嘗試導入 tqdm，如果沒有則使用降級方案
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("💡 提示: 安裝 tqdm 可獲得進度條顯示 (pip install tqdm)\n")

# 設定
VIDEO_DIR = 'video'
SUBTITLE_DIR = 'subtitle'
MODEL_FILE = 'ggml-large-v3.bin'
SUPPORTED_EXTENSIONS = {'.mp4', '.mov', '.m4a', '.mp3', '.mkv', '.wav'}


def check_dependencies():
    """檢查必要的依賴是否存在"""
    errors = []
    
    # 檢查 ffmpeg
    if not shutil.which('ffmpeg'):
        errors.append("❌ 找不到 ffmpeg，請先安裝 ffmpeg")
    
    # 檢查 whisper.cpp 的 main 執行檔
    if not shutil.which('main'):
        errors.append(f"❌ 找不到 whisper.cpp 的 main 執行檔")
    
    # 檢查模型檔案
    if not os.path.isfile(MODEL_FILE):
        errors.append(f"❌ 找不到模型檔案: {MODEL_FILE}")
    
    # 檢查 video 目錄
    if not os.path.isdir(VIDEO_DIR):
        errors.append(f"❌ 找不到輸入目錄: {VIDEO_DIR}/")
    
    if errors:
        print("\n".join(errors))
        return False
    
    return True


def extract_audio_with_filters(input_file: str, output_file: str) -> bool:
    """
    使用 ffmpeg 提取並優化音頻
    - 單聲道 (mono)
    - 16kHz 採樣率
    - PCM 16-bit 編碼
    - 音頻濾鏡：loudnorm + highpass + lowpass（提高識別準確度）
    
    Args:
        input_file: 輸入影片/音頻檔案路徑
        output_file: 輸出 WAV 檔案路徑
    
    Returns:
        True 如果成功，False 如果失敗
    """
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-ar', '16000',
        '-ac', '1',
        '-c:a', 'pcm_s16le',
        '-af', 'loudnorm,highpass=f=80,lowpass=f=8000',
        output_file
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 音頻提取失敗: {e}")
        return False


def generate_subtitle(wav_file: str, output_srt: str) -> bool:
    """
    使用 whisper.cpp 生成字幕
    
    Args:
        wav_file: 輸入 WAV 檔案路徑
        output_srt: 輸出 SRT 字幕檔案路徑
    
    Returns:
        True 如果成功，False 如果失敗
    """
    # whisper.cpp 會自動在 wav 檔名後加 .srt
    temp_srt = f"{wav_file}.srt"
    
    cmd = (
        f'chcp 65001 && main -m {MODEL_FILE} '
        f'--prompt "使用繁體中文" -f "{wav_file}" -l zh -osrt'
    )
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        
        # 移動字幕檔案到目標位置
        if os.path.isfile(temp_srt):
            shutil.move(temp_srt, output_srt)
            return True
        else:
            print(f"  ❌ 未生成字幕檔案: {temp_srt}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 字幕生成失敗: {e}")
        return False


def process_video(video_path: str, subtitle_dir: str, show_status: bool = True) -> bool:
    """
    處理單個影片檔案，生成字幕
    
    Args:
        video_path: 影片檔案完整路徑
        subtitle_dir: 字幕輸出目錄
        show_status: 是否顯示處理狀態訊息
    
    Returns:
        True 如果成功，False 如果失敗或跳過
    """
    video_path_obj = Path(video_path)
    file_name = video_path_obj.name
    file_stem = video_path_obj.stem
    file_ext = video_path_obj.suffix.lower()
    
    # 檢查副檔名
    if file_ext not in SUPPORTED_EXTENSIONS:
        return False
    
    # 計算相對路徑以保持目錄結構
    rel_path = video_path_obj.relative_to(VIDEO_DIR)
    output_srt_path = Path(subtitle_dir) / rel_path.parent / f"{file_stem}.srt"
    
    # 如果字幕已存在，跳過
    if output_srt_path.exists():
        return False
    
    # 建立輸出目錄
    output_srt_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 臨時 WAV 檔案路徑
    temp_wav = video_path_obj.parent / f"{file_stem}_temp.wav"
    keep_wav = (file_ext == '.wav')
    
    try:
        # 步驟 1: 提取音頻（如果不是已存在的 WAV）
        if not keep_wav or not video_path_obj.exists():
            if show_status:
                if TQDM_AVAILABLE:
                    tqdm.write("  ⏳ 提取音頻...")
                else:
                    print("  ⏳ 提取音頻...")
            if not extract_audio_with_filters(str(video_path), str(temp_wav)):
                return False
        else:
            temp_wav = video_path_obj
        
        # 步驟 2: 生成字幕
        if show_status:
            if TQDM_AVAILABLE:
                tqdm.write("  🤖 生成字幕...")
            else:
                print("  🤖 生成字幕...")
        success = generate_subtitle(str(temp_wav), str(output_srt_path))
        
        # 清理臨時 WAV 檔案
        if not keep_wav and temp_wav.exists():
            temp_wav.unlink()
        
        return success
        
    except Exception as e:
        print(f"  ❌ 處理失敗: {e}")
        # 清理臨時檔案
        if not keep_wav and temp_wav.exists():
            temp_wav.unlink()
        return False


def collect_video_files(video_dir: str) -> List[str]:
    """收集所有需要處理的影片檔案"""
    video_files = []
    for root, dirs, files in os.walk(video_dir):
        for file in files:
            file_path = os.path.join(root, file)
            ext = Path(file_path).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                # 檢查是否已有字幕
                rel_path = Path(file_path).relative_to(video_dir)
                srt_path = Path(SUBTITLE_DIR) / rel_path.parent / f"{Path(file_path).stem}.srt"
                if not srt_path.exists():
                    video_files.append(file_path)
    
    return video_files


def main():
    """主程式"""
    print("=" * 60)
    print("影片字幕自動生成工具 (whisper.cpp + 音頻濾鏡優化)")
    print("=" * 60)
    
    # 檢查依賴
    if not check_dependencies():
        sys.exit(1)
    
    # 建立字幕輸出目錄
    os.makedirs(SUBTITLE_DIR, exist_ok=True)
    
    # 收集所有影片檔案
    print(f"\n📁 掃描 {VIDEO_DIR}/ 目錄...")
    video_files = collect_video_files(VIDEO_DIR)
    
    if not video_files:
        print(f"✅ 沒有需要處理的影片檔案（可能都已生成字幕）")
        return
    
    print(f"📊 找到 {len(video_files)} 個需要處理的影片檔案\n")
    
    # 處理影片
    success_count = 0
    failed_count = 0
    
    if TQDM_AVAILABLE:
        # 使用 tqdm 顯示進度條
        for video_file in tqdm(video_files, desc="生成字幕", unit="個", ncols=80):
            rel_name = Path(video_file).relative_to(VIDEO_DIR)
            tqdm.write(f"\n🎬 {rel_name}")
            if process_video(video_file, SUBTITLE_DIR, show_status=True):
                success_count += 1
                tqdm.write(f"✅ 完成\n")
            else:
                failed_count += 1
                tqdm.write(f"⏭️  跳過\n")
    else:
        # 降級方案：顯示詳細進度
        total = len(video_files)
        for i, video_file in enumerate(video_files, 1):
            rel_name = Path(video_file).relative_to(VIDEO_DIR)
            print(f"\n[{i}/{total}] 🎬 {rel_name}")
            if process_video(video_file, SUBTITLE_DIR, show_status=False):
                success_count += 1
                print(f"✅ 完成 ({i}/{total})")
            else:
                failed_count += 1
                print(f"⏭️  跳過")
    
    # 顯示統計結果
    print("\n" + "=" * 60)
    print(f"✅ 成功: {success_count} 個")
    if failed_count > 0:
        print(f"❌ 失敗: {failed_count} 個")
    print(f"📂 字幕已儲存至: {SUBTITLE_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()