import sys
from pathlib import Path

# 保证从 data/ 目录直接运行本脚本时也能 import 项目根目录下的 config
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import pymysql
from config import Config
import pandas as pd

conn = pymysql.connect(
    host=Config.host,
    user=Config.user,
    password=Config.password,
    database=Config.db,
)

cursor = conn.cursor()

# 相对项目根目录，不依赖「从哪一级目录执行 python」时的当前工作目录
LSTM_RESULT = _ROOT / "build_model" / "LSTM_result.csv"
df = pd.read_csv(LSTM_RESULT)

sql = 'insert into myapp_commentinfo(comment_text,area,gender,fans_num,follow_num,pub_num,comment_date,keyword,lstm_result,lstm_score) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'

for index, row in df.iterrows():
    cursor.execute(sql, tuple(row))
conn.commit()
