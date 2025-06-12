import pymysql
import pandas as pd

# 1) DB 연결 정보 설정
conn = pymysql.connect(
    host='localhost',      # MySQL 호스트
    port=3306,             # 포트 (기본: 3306)
    user='root',  # MySQL 사용자명
    password='smart001!',  # MySQL 비밀번호
    database='ITS_TS',    # 사용할 데이터베이스
    charset='utf8mb4'
)

try:
    # 2) 조회할 SQL 작성
    sql = """
    SELECT
      sensor_pk,
      device_id,
      channel,
      d_type
    FROM sensor;
    """

    # 3) pandas로 바로 읽어오기
    df = pd.read_sql(sql, conn)

    # 4) 결과 출력 (또는 Dash 콜백에서 사용)
    print(df)

finally:
    conn.close()