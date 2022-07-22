# find /data/project/zhmrtbot/public_html/file/* -mtime +179 -type f -delete
from datetime import datetime
import logging
import os
import time
import savepagenow
# pylint: disable=W0703, C0301


logging.basicConfig(level=logging.INFO)
s_curtime = datetime.utcnow()

dir_path = "/data/project/zhmrtbot/public_html/file"
NO_EXT = ["tgs"]
LIMIT = 179
ntime = time.time() # time for now

files = os.listdir(dir_path)
cnt = 0
retry = 0
for f in files:
    f_path = f"{dir_path}/{f}"
    mtime = os.path.getmtime(f_path)
    ext = f.split(".")[1].lower() if len(f.split(".")) == 2 else ""
    if ntime - mtime > LIMIT * 24 * 60 * 60 and ext not in NO_EXT:
        url = f"https://zhmrtbot.toolforge.org/file/{f}"
        while True:
            try:
                a_url = savepagenow.capture_or_cache(url)
                rerty = 0
                break
            except Exception:
                print(f"HTTP429, retry {retry + 1}")
                time.sleep(30 * pow(2, retry))
                retry += 1

        time.sleep(15)
        cnt += 1
        curtime_ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        logging.info("%s [%d] %s", curtime_ts, cnt, a_url)
        if os.path.isfile(f_path):
            os.remove(f_path)

if cnt > 0:
    e_curtime = datetime.utcnow()
    e_curtime_ts = e_curtime.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{e_curtime_ts} Archived {cnt} files in {(e_curtime - s_curtime).total_seconds()} seconds")
