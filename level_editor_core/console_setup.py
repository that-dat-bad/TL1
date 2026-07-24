import sys
import io
import os

def setup_console_encoding():
    # Blenderのコンソール出力をUTF-8に設定（Windows文字化け対策）
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    if sys.platform == 'win32':
        try:
            import ctypes
            # Windowsコンソールの出力コードページをUTF-8(65001)に変更
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass

    # stdout/stderrのエンコーディングをUTF-8に再設定
    try:
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        elif sys.stdout and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
    try:
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
        elif sys.stderr and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
