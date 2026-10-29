"""One asynchronous quote fetch per server, shared by viewers; old trade times stay old."""
import threading,time
from .desk_quotes import LiveFeed,channel


class QuoteHub:
    def __init__(self,feed=None,interval=5):
        self.feed=feed or LiveFeed(timeout=3,cooldown=15);self.interval=interval
        self.lock=threading.RLock();self.rows={};self.running=False;self.last_start=-1e9
        self.last_received='';self.error='';self.attempts=0

    def get(self,stocks,enabled=True,clock=time.monotonic):
        keys=[str(r['ticker']) for r in stocks][:50]
        with self.lock:
            if enabled and not self.running and clock()-self.last_start>=self.interval:
                self.running=True;self.last_start=clock();self.attempts+=1
                channels=[channel(str(r['ticker']),r['board']) for r in stocks[:50]]
                def run():
                    from .auto_market import now
                    try:
                        data=self.feed.fetch(channels);rows={str(r['ticker']):r for r in data.to_dict('records')}
                        with self.lock:
                            self.rows.update(rows);self.error=self.feed.error
                            if rows:self.last_received=now()
                    except Exception:
                        with self.lock:self.error='報價暫未取得，保留前次成交時間'
                    finally:
                        with self.lock:self.running=False
                threading.Thread(target=run,daemon=True,name='quotes-5-second').start()
            return {t:dict(self.rows[t]) for t in keys if t in self.rows}
