import datetime
import logging
import pyupbit
from time import sleep

logging.basicConfig(filename="trade_log.txt", level=logging.INFO)


class BitBot(pyupbit.Upbit):

    def __init__(self, api_key): # api_key : dict 형태 --> api_key['access', 'secret']
        super().__init__(api_key['access'], api_key['secret'])
        self.ticker_list = pyupbit.get_tickers(fiat="KRW")  # 거래가능한 KRW 코인 추출
        self.account_info = self.get_balances()
        self.monitoring_list = dict()

        for ticker in self.ticker_list:
            self.monitoring_list[ticker] = 0

        """ 구조 재조정 필요
        self.monitoring_list = dict()
        
        monitoring_list 구조
            코인심볼명(key) : 피라미딩레벨(value), 현재매수가(value),
                            다음목표매수가(value), 손절가(value) 
        """

    def get_monitoring_list(self):
        return self.monitoring_list

    def set_monitoring_list(self, ticker, price, gubun=0):  # 0:add 1:edit 2:del
        pass

    def get_current_ohlc(self, ticker):
        data = pyupbit.get_daily_ohlcv_from_base(ticker, base=9).iloc[-1]
        return data['open'], data['high'], data['low'], data['close']

    def get_order_book(self, ticker, position, slippage=2):
        # ticker : 코인심볼명, postition : 매매방향, slippage : 호가레벨최대허용치
        # 슬리피지 기본값은 최대 2틱

        orderbook_list = pyupbit.get_orderbook(ticker)
        bids_asks = orderbook_list[0]['orderbook_units']

        if position == "BUY":
            return float(bids_asks[slippage-1]['ask_price'])

        elif position == "SELL":
            return float(bids_asks[slippage-1]['bid_price'])

    def buy_order(self, ticker, order_price, maximum_price):
        quant_size = maximum_price / order_price
        # msg = ticker, order_price, quant_size, " BUY"
        ret = self.buy_limit_order(ticker, order_price, quant_size)
        return ret

    def sell_order(self, ticker, order_price):
        quant_size = 0

        for asset in self.get_balances():  # 가지고 있는 자산 조회
            if asset['currency'] == ticker[4:]:
                quant_size = float(asset['balance'])

        if quant_size > 0:
            msg = ticker, order_price, quant_size, " SELL"
            ret = self.sell_limit_order(ticker, order_price, quant_size)
            return ret

    def scan(self, ticker):
        # open high low close 값
        # 해당 코인 count 일 만큼 시고저종값 가져옴

        open, high, low, close = self.get_current_ohlc(ticker)

        # note : 고가는 종가와 5% 이상 차이나면 안됨, 윗꼬리 길면 전량매도

        open_high_rate = float((high - open) / open)    # 시가에서 고가 변동률
        open_close_rate = float((close - open) / open)  # 시가에서 종가 변동률
        close_high_rate = float((high - close) / close)  # 종가에서 고가까지 변동률

        corrected_value = self.monitoring_list[ticker] * 0.01  # 피라미딩 레벨에 따른 변동률 허용치 추가

        msg = f"{ticker} 시고:{open_high_rate:.3f}, 시종:{open_close_rate:.3f}, 종고:{close_high_rate:.3f}{open, high, low, close}"

        if open_high_rate > 0.05 and False:  # 임시로 만든것들
            print(msg)

        # 시가 대비 (5% + 피라미딩 레벨에 따른 변동률 보정값) ~ (6% + 피라미딩 레벨에 따른 변동률 보정값) 일때
        condition_1_1 = (0.05 + corrected_value < open_close_rate < 0.06 + corrected_value)
        condition_1_2 = close_high_rate < 0.05  # 고가 대비 종가가 5% 이하일 경우(고가와 종가가 변동이 거의 없는 경우)

        if condition_1_1 and condition_1_2:
            if self.monitoring_list[ticker] < 10:
                self.monitoring_list[ticker] += 1
                logging.info("[BUY]  "+msg)
                print("[BUY]  "+msg)
                return "BUY"

        # 피라미딩 레벨이 0 이상이고 (매수를 해야 피라미딩이 오르므로, 매수구분 변수로 사용)
        # 시가 대비 고가 10% 이상 찍고, 고가 대비 종가가 5% 이상 하락 했거나
        condition_2_1 = (self.monitoring_list[ticker] > 0)
        condition_2_2 = (open_high_rate > 0.10 and close_high_rate < -0.05)
        condition_2_3 = open_close_rate < 0.04  # 시가 대비 종가가 4% 이상 하락했을때(매매가 기준 1% 하락됐을때임)

        if condition_2_1 and (condition_2_2 or condition_2_3):
            if self.monitoring_list[ticker] > 0:
                self.monitoring_list[ticker] = 0
                logging.info("[SELL] "+msg)
                print("[SELL] " + msg)
                return "SELL"

    def run(self):
        my_krw = self.get_balance("KRW")

        for ticker in self.ticker_list:  # 거래가능한 모든 코인리스트 만큼 반복

            flag = self.scan(ticker)

            if flag == "BUY":
                best_price = self.get_order_book(ticker, "BUY")  # 슬리피지 적용한 매수가
                self.buy_order(ticker, best_price, my_krw)  # 심볼, 주문적정가, 보유금액(주문가능최대금액)

            elif flag == "SELL":
                best_price = self.get_order_book(ticker, "SELL")  # 슬리피지 적용한 매도가
                self.sell_order(ticker, best_price)

            sleep(0.07)


if __name__ == "__main__":

    api_keys = {
        "access": "(Access Key 입력)",
        "secret": "(Secret Key 입력)"
    }

    Bot = BitBot(api_keys)

    while True:
        now = datetime.datetime.now()
        mid = datetime.datetime(now.year, now.month, now.day) + \
            datetime.timedelta(1)

        while True:  # 다음 날까지 Bot.run() 반복
            now = datetime.datetime.now()

            Bot.run()

            if now >= mid:
                break
