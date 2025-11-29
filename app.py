import platform
import subprocess
import time
import os
from datetime import datetime

sites = ["google.com", "facebook.com", "github.com", "goooogle.com"]
log_file = "logs/ping_log.txt"

os.makedirs("logs", exist_ok=True)


def ping(host):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', host]
    try:
        subprocess.check_call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def write_log(message):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def main():
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for site in sites:
            status = "UP" if ping(site) else "DOWN"
            log_message = f"[{timestamp}] {site}: {status}"
            print(log_message)
            write_log(log_message)

        time.sleep(60)


if __name__ == "__main__":
    main()