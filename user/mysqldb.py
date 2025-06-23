import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from logger import Logger as log

class Mysqlhandler:
    def __init__(self, host, user, password, db_name):
        self.host = host
        self.user = user
        self.password = password
        self.db_name = db_name
        self.engine = None
        self.Session = None

    def connect(self):
        try:
            self.engine = create_engine(f"mysql+mysqlconnector://{self.user}:{self.password}@{self.host}/{self.db_name}")
            self.Session = sessionmaker(bind=self.engine)
            log.info('mysql) (connect) host={} db_name={}'.format(self.host, self.db_name))
        except Exception as e:
            log.error(str(e))

    def close(self):
        if self.engine:
            self.engine.dispose()

    def do_select(self, query_str, params=None):
        if query_str == '':
            log.info('Empty Query String')
            return []

        session = self.Session()
        try:
            if params is None:
                result = session.execute(query_str)
            else:
                result = session.execute(query_str, params)
            rows = result.fetchall()
        except Exception as e:
            log.error(e)
            rows = []
        finally:
            session.close()

        return rows

    def do_select_pd(self, query_str, params=None):
        if query_str == '':
            log.info('Empty Query String')
            return pd.DataFrame()

        try:
            df = pd.read_sql(query_str, self.engine, params=params)
        except Exception as e:
            log.error(e)
            df = pd.DataFrame()

        return df

    def do_sql(self, sql):
        if sql == '':
            log.info('Empty Query String')
            return

        session = self.Session()
        try:
            session.execute(sql)
            session.commit()
        except Exception as e:
            log.error(e)
        finally:
            session.close()

    def execute(self, sql, data):
        if sql == '':
            log.info('Empty Query String')
            return

        session = self.Session()
        try:
            result = session.execute(sql, data)
            session.commit()
            return result.fetchall()
        except Exception as e:
            log.error(e)
            return []
        finally:
            session.close()

    def executemany(self, sql, data):
        if sql == '':
            log.info('Empty Query String')
            return

        session = self.Session()
        try:
            session.executemany(sql, data)
            session.commit()
        except Exception as e:
            log.error(e)
        finally:
            session.close()
