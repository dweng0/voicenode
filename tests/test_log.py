import subprocess
from pathlib import Path
import time
import signal


def test_log_no_file():
    """Test log command when log file doesn't exist."""
    log_path = Path("logs/voicenode.log")
    log_path.unlink(missing_ok=True)
    
    result = subprocess.run(
        ["voicenode", "log"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert "No logs found" in result.stdout


def test_log_with_file():
    """Test log command with existing log file."""
    log_path = Path("logs/voicenode.log")
    log_path.parent.mkdir(exist_ok=True)
    
    test_lines = [
        '{"event": "test1", "level": "info"}',
        '{"event": "test2", "level": "info"}',
        '{"event": "test3", "level": "info"}',
    ]
    
    with open(log_path, "w") as f:
        for line in test_lines:
            f.write(line + "\n")
    
    proc = subprocess.Popen(
        ["voicenode", "log", "-n", "2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    time.sleep(0.5)
    
    proc.send_signal(signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=5)
    
    assert '{"event": "test2"' in stdout
    assert '{"event": "test3"' in stdout
    
    log_path.unlink(missing_ok=True)


def test_log_follow():
    """Test log command follows new entries."""
    log_path = Path("logs/voicenode.log")
    log_path.parent.mkdir(exist_ok=True)
    
    with open(log_path, "w") as f:
        f.write('{"event": "initial", "level": "info"}\n')
    
    proc = subprocess.Popen(
        ["voicenode", "log"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    time.sleep(0.5)
    
    with open(log_path, "a") as f:
        f.write('{"event": "new_line", "level": "info"}\n')
    
    time.sleep(0.5)
    
    proc.send_signal(signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=5)
    
    log_path.unlink(missing_ok=True)
    
    assert '{"event": "initial"' in stdout
    assert '{"event": "new_line"' in stdout