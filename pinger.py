from icmplib import async_ping
import asyncio
import time
import db
import json


class Pinger:
    """
    Класс пингера на основе библиотеки icmplib использует асинхронный подход,
    имеет 5 методов:

    - выполнить пинг всех хостов в БД
    - выполнить пинг одного хоста по IP
    - изменить время цикла автоматического пинга хостов
    - изменть кол-во отправленных icmp на один хост (по умолчанию - 3)
    - изменть timeout ответа icmp от хоста (по умаолчанию - 1 сек)

    При создании класса, конструктор сразу создаёт ассинхронную задачу,
    пинг всех хостов в цикле
    """

    def __init__(self):

        self.parent_server = None
        self.loop = asyncio.get_event_loop()
    
    def set_parent_server(self, parent):
        self.parent_server = parent
    
    def set_icmp_params(self, auto_ping, icmp_with_host, icmp_interval, ping_hosts_per_sec, icmp_timeout):
        self._AUTO_PING_INTERVAL = auto_ping
        self._ICMP_COUNT = icmp_with_host
        self._ICMP_INTERVAL = icmp_interval
        self._ICMP_PER_SECOND = ping_hosts_per_sec
        self._ICMP_TIMEOUT = icmp_timeout

    def run_ping_loop(self) -> None:
        self.loop.create_task(self._run_auto_ping())

    async def _icmp_ping_host(self, ip):
        try:
            hst = db.one_info(ip)  # вся инфа о хосте
            if hst[3] == 'offline':
                db.change_state(ip, 'clock.offline')
            elif hst[3] == 'online':
                db.change_state(ip, 'clock.online')

            host = await async_ping(ip,
                                    count=self._ICMP_COUNT,
                                    interval=self._ICMP_INTERVAL,
                                    timeout=self._ICMP_TIMEOUT)

            current_time = int(time.time())

            if host.is_alive:
                # если хост ответил на icmp
                self.parent_server.log.icmp_good(hst)  # ЛОГ
                if hst[3] == 'offline' or hst[3] == 'clock.offline':
                    db.change_time(ip, current_time)
                    self.parent_server.log.change_state(f'Хост <{hst[0]}> {hst[1]}  [включился]')
                    if hst[6]:
                        try:
                            sms_data = json.loads(hst[6])
                            if sms_data['online']:
                                self.loop.create_task(self.send_sms(sms_data['online_url']))
                                self.parent_server.log.alarm(f'SMS оповещение о включении хоста <{ip}> отправлено')
                        except (Exception,):
                            pass
                db.change_state(ip, 'online')

            else:
                # если хост не ответил на icmp
                self.parent_server.log.icmp_bad(hst)  # ЛОГ
                if hst[3] == 'online' or hst[3] == 'clock.online':
                    db.change_time(ip, current_time)
                    self.parent_server.log.change_state(f'Хост <{hst[0]}> {hst[1]}  [отключился]')
                    if hst[6]:
                        try:
                            sms_data = json.loads(hst[6])
                            if sms_data['offline']:
                                if sms_data['double_check']:
                                    self.loop.create_task(self.check_host_sms(ip, sms_data['offline_url']))
                                else:
                                    self.loop.create_task(self.send_sms(sms_data['offline_url']))
                        except (Exception,):
                            pass
                db.change_state(ip, 'offline')
        except (Exception,):
            return

    async def check_host_sms(self, ip, url):
        """Дополнительная проверка хоста перед отправкой sms"""
        await asyncio.sleep(30)
        try:
            host = await async_ping(ip, count=5, interval=1, timeout=1)
            if host.is_alive:
                return
            else:
                await self.send_sms(url)
                self.parent_server.log.alarm(f'SMS оповещение об отключении хоста <{ip}> отправлено')
                return
        except (Exception,):
            await self.send_sms(url)
            self.parent_server.log.alarm(f'SMS оповещение об отключении хоста <{ip}> отправлено')

    @staticmethod
    async def send_sms(url):
        """Отправка sms"""
        pass

    async def _ping_all(self, show_alarm=True):
        # пинг всех хостов в БД
        all_hosts = db.all_info()
        if show_alarm:
            self.parent_server.log.alarm('Через 10 секунд начнётся плановая проверка всех хостов')
            await asyncio.sleep(10)
        if all_hosts:
            for c, host in enumerate(all_hosts):
                if host[3] != 'pause':
                    self.loop.create_task(self._icmp_ping_host(host[0]))
                    await asyncio.sleep(1 / self._ICMP_PER_SECOND)

    async def _ping_one(self, ip):
        # поиск хоста по IP в БД, если найден, тогда отправить пинг
        self.loop.create_task(self._icmp_ping_host(ip))

    async def _run_auto_ping(self):
        # цикл автоматического пинга всех хостов, с определённым интервалом
        while True:
            self.loop.create_task(self._ping_all())
            await asyncio.sleep(self._AUTO_PING_INTERVAL)  # интервал итараций цикла

    def start_ping_all(self):
        self.loop.create_task(self._ping_all(show_alarm=False))

    def start_ping_one(self, ip):
        self.loop.create_task(self._ping_one(ip))

    def start_ping_dead(self):
        hosts = db.all_info()
        for host in hosts:
            if host[3] == 'offline' or host[3] == 'clock.offline':
                self.start_ping_one(host[0])

    def set_icmp_interval(self, seconds):
        self._ICMP_INTERVAL = seconds

    def set_icmp_timeout(self, seconds):
        self._ICMP_TIMEOUT = seconds

    def set_auto_ping_interval(self, seconds):
        self._AUTO_PING_INTERVAL = seconds

    def set_icmp_count(self, count):
        self._ICMP_COUNT = count

    def set_icmp_per_second(self, count):
        self._ICMP_PER_SECOND = count