import socket
import os
import sys
import time
import asyncio
import json
import datetime
import struct
import db
from icmplib import async_ping
import zlib


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

    def __init__(self, auto_ping, icmp_with_host, icmp_interval, ping_hosts_per_sec, icmp_timeout, parent_server):
        self._AUTO_PING_INTERVAL = auto_ping
        self._ICMP_COUNT = icmp_with_host
        self._ICMP_INTERVAL = icmp_interval
        self._ICMP_PER_SECOND = ping_hosts_per_sec
        self._ICMP_TIMEOUT = icmp_timeout

        self.parent_server = parent_server

        self.loop = asyncio.get_event_loop()
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


class Protocol:
    """Протокол передачи данных поверх TCP
    Суть проста, пакет состоит из двух полей: HEADER и DATA
    - header служит для обозначения длинны пакета в байтах, передаётся в виде STRUCT int (Си)
    - в data содержится само передаваемое сообщение

    Протокол устойчив к работе с медленной сетью, так как построен на TCP.
    Работает на основе asyncio"""

    def __init__(self):
        """
        Получить текущий EventLoop
        """
        self.loop = asyncio.get_event_loop()

    async def recv_offset(self, sock, len_packet):
        # считывать буфер сокета операционной системы до тех пор,
        # пока нужное количество байт не будет собрано в пакет
        packet = b''
        while len(packet) < len_packet:
            try:
                data = await self.loop.sock_recv(sock, len_packet - len(packet))
                if not data:
                    return
                packet += data
            except OSError:
                return
        return packet

    async def recv(self, sock):
        # возращает пакет переданный по tcp socket
        # в случае ошибки вернёт None
        try:
            header = await self.recv_offset(sock, 4)
            len_packet = struct.unpack('<I', header)[0]
            packet = await self.recv_offset(sock, len_packet)
            return zlib.decompress(packet)
        except struct.error:
            return
        except TypeError:
            return

    async def send_all(self, sock, msg):
        try:
            msg = zlib.compress(msg.encode('utf-8'))  # zip-сжатие строки
            header = struct.pack('<I', len(msg))
            await self.loop.sock_sendall(sock, header + msg)
        except (OSError, TypeError, struct.error):
            pass


class RequestHandler:
    """
    Обработчик запросов от клиентов
    Основная суть состоит в обработке запроса и отправки ответа на него
    В основном вся логика построена вокруг БД
    """
    requests = ['GET', 'POST', 'PUT', 'DELETE', 'SERVICE']
    objects = ['FOLDER', 'HOST', 'USER']
    bad_request = json.dumps({'response': 100, 'data': 'bad request'})

    def __init__(self, parent):
        self.parent = parent

    def handler(self, request, login, access='guest'):
        try:
            req = json.loads(request)
            type_req = req['request']
            if type_req in self.requests:
                if type_req == 'GET':
                    return self.get(req)
                elif type_req == 'POST':
                    if access == 'admin':
                        return self.post(req, login, access)
                    else:
                        self.parent.log.user_event(login, access, '0.0.0.0', 'Не достаточно прав для выполнения запроса: <create>')
                        return self.no_permissions()
                elif type_req == 'PUT':
                    if access == 'admin':
                        return self.put(req, login, access)
                    else:
                        self.parent.log.user_event(login, access, '0.0.0.0', 'Не достаточно прав для выполнения запроса: <update>')
                        return self.no_permissions()
                elif type_req == 'DELETE':
                    if access == 'admin':
                        return self.delete(req, login, access)
                    else:
                        self.parent.log.user_event(login, access, '0.0.0.0', 'Не достаточно прав для выполнения запроса: <delete>')
                        return self.no_permissions()
                elif type_req == 'SERVICE':
                    return self.service(req, login, access)
            else:
                return self.bad_request
        except (json.JSONDecodeError, Exception):
            return self.bad_request

    def get(self, r):
        try:
            if r['object'] == 'HOST':
                item = r['item']
                if item == 'all':
                    return json.dumps({'response': 200, 'data': db.all_info()})

                elif item == 'dead':
                    dead_hosts = []
                    hosts = db.all_info()
                    for host in hosts:
                        if host[3] == 'offline' or host[3] == 'clock.offline':
                            dead_hosts.append(host)
                    return json.dumps({'response': 200, 'data': dead_hosts})

                elif item == 'live':
                    live_hosts = []
                    hosts = db.all_info()
                    for host in hosts:
                        if host[3] == 'online' or host[3] == 'clock.online':
                            live_hosts.append(host)
                    return json.dumps({'response': 200, 'data': live_hosts})

                elif item == 'pause':
                    pause_hosts = []
                    hosts = db.all_info()
                    for host in hosts:
                        if host[3] == 'pause':
                            pause_hosts.append(host)
                    return json.dumps({'response': 200, 'data': pause_hosts})

                else:
                    data = db.one_info(item['ip'])
                    if data == 'not found':
                        return json.dumps({'response': 300, 'data': 'not exists'})
                    elif data == 'unknown error':
                        return json.dumps({'response': 500, 'data': data})
                    else:
                        return json.dumps({'response': 200, 'data': data})

            elif r['object'] == 'FOLDER':
                item = r['item']
                if item == 'all':
                    return json.dumps({'response': 200, 'data': db.load_folders()})
                elif db.check_folder_(item['folder_id']):
                    hosts_in_folder = []
                    hosts = db.all_info()
                    for host in hosts:
                        if host[2] == item['folder_id']:
                            hosts_in_folder.append(host)
                    return json.dumps({'response': 200, 'data': hosts_in_folder})
                else:
                    return json.dumps({'response': 300, 'data': 'not exists'})

            elif r['object'] == 'USER':
                item = r['item']
                if item == 'online':
                    cl = [self.parent.clients[i] for i in self.parent.clients]
                    return json.dumps({'response': 200, 'data': cl})
                elif item == 'registered':
                    users = db.registered_users()
                    if users:
                        _users = []
                        for user in users:
                            # убрать пароли
                            _users.append((user[0], user[2], user[3]))
                        return json.dumps({'response': 200, 'data': _users})
                    else:
                        return json.dumps({'response': 500, 'data': ''})

            elif r['object'] == 'PINGER':
                ping_params = db.icmp_params()
                if ping_params:
                    return json.dumps({'response': 200, 'data': ping_params})
                else:
                    return json.dumps({'response': 500, 'data': ''})

            elif r['object'] == 'PHONE':
                phones = db.phone_numbers()
                if phones:
                    return json.dumps({'response': 200, 'data': phones})
                else:
                    return json.dumps({'response': 500, 'data': ''})

            elif r['object'] == 'SMS_API':
                sms_api = db.sms_api()
                if sms_api:
                    return json.dumps({'response': 200, 'data': sms_api})
                else:
                    return json.dumps({'response': 500, 'data': ''})

            elif r['object'] == 'LOG_FILE':
                sms_api = db.sms_api()
                if sms_api:
                    return json.dumps({'response': 200, 'data': sms_api})
                else:
                    return json.dumps({'response': 500, 'data': ''})

            else:
                return self.bad_request
        except (OSError, Exception):
            return self.bad_request

    def post(self, r, login, access):
        try:
            if r['object'] == 'HOST':
                item = r['item']
                d = db.insert_host(
                    item['ip'],
                    item['name'],
                    item['folder_id'],
                    item['state'],
                    time.time(),
                    item['info'],
                    None
                )

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.host exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                else:
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''добавил новый хост <{item['ip']}>''')
                    return json.dumps({'response': 200, 'data': 'DB.success'})

            elif r['object'] == 'FOLDER':
                item = r['item']
                try:
                    d = db.create_folder(
                        str(max([int(i[0]) for i in db.load_folders()]) + 1),  # генерация уникального id
                        item['name']
                    )
                except (Exception,):
                    d = db.create_folder(1, item['name'])

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.folder exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                elif d == 'success':
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''создал новую папку <{item['name']}>''')
                    return json.dumps({'response': 200, 'data': 'DB.success'})

            elif r['object'] == 'USER':
                item = r['item']
                d = db.create_user(item['login'], item['passw'], item['access'])

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.user exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                elif d == 'success':
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''создал нового пользователя <{item['login']}>''')
                    return json.dumps({'response': 200, 'data': 'DB.success'})

            elif r['object'] == 'PHONE':
                item = r['item']
                d = db.create_phone_number(item['number'], item['info'])

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.phone exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                elif d == 'success':
                    return json.dumps({'response': 200, 'data': 'DB.success'})
            else:
                return self.bad_request
        except (OSError, Exception):
            return self.bad_request

    def put(self, r, login, access):
        try:
            if r['object'] == 'HOST':
                item = r['item']

                h = db.one_info(item['new']['ip'])
                if h == 'not found':

                    h = db.one_info(item['ip'])
                    if h == 'not found':
                        return json.dumps({'response': 300, 'data': 'ip not exists'})

                    if item['new']['name']:
                        result = db.change_name(item['ip'], item['new']['name'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_name.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0',
                                       f'''изменил имя хоста <{item['ip']}> на "{item['new']['name']}"''')

                    if item['new']['folder_id']:
                        result = db.change_folder(item['ip'], item['new']['folder_id'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0', f'''изменил ID папки хоста <{item['ip']}>''')

                    if item['new']['state']:
                        result = db.change_state(item['ip'], item['new']['state'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_state.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0',
                                       f'''изменил состояние хоста <{item['ip']}> на {item['new']['state']}''')

                    if item['new']['info']:
                        result = db.change_info(item['ip'], item['new']['info'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_info.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0', f'''изменил информацию о хосте <{item['ip']}>''')

                    if item['new']['sms']:
                        result = db.change_sms(item['ip'], item['new']['sms'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_sms.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0', f'''изменил SMS оповещения хоста <{item['ip']}>''')

                    elif item['new']['sms'] == '':
                        result = db.change_sms(item['ip'], None)
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_sms.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0', f'''изменил SMS оповещения хоста <{item['ip']}>''')

                    if item['new']['ip']:
                        result = db.change_ip(item['ip'], item['new']['ip'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_ip.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0',
                                       f'''изменил IP хоста <{item['ip']}> на <{item['new']['ip']}>''')

                    return json.dumps({'response': 200, 'data': 'success'})
                else:
                    return json.dumps({'response': 700, 'data': 'new ip already exists'})

            elif r['object'] == 'FOLDER':
                item = r['item']
                if db.check_folder_(item['folder_id']):
                    if item['new']['name']:
                        d = db.change_name_folder(item['folder_id'], item['new']['name'])
                        if not d == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})
                        self.parent.log.user_event(login, access, '0.0.0.0',
                                       f'''изменил название папки с id <{item['folder_id']}> на "{item['new']['name']}"''')

                    if item['new']['folder_id']:
                        if db.check_folder_(item['new']['folder_id']):
                            return json.dumps({'response': 700, 'data': 'id folder already exists'})
                        else:
                            d = db.change_id_folder(item['folder_id'], item['new']['folder_id'])
                            if d == 'success':
                                self.parent.log.user_event(login, access, '0.0.0.0',
                                               f'''отредактировал папку с id <{item['folder_id']}>''')
                                return json.dumps({'response': 200, 'data': 'DB.change_folder.success'})
                            else:
                                return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})

                    return json.dumps({'response': 200, 'data': 'no changes'})
                else:
                    return json.dumps({'response': 300, 'data': 'folder not exists'})

            elif r['object'] == 'USER':
                item = r['item']
                if db.check_folder_(item['folder_id']):
                    if item['new']['name']:
                        d = db.change_name_folder(item['folder_id'], item['new']['name'])
                        if not d == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})

                    if item['new']['folder_id']:
                        if db.check_folder_(item['new']['folder_id']):
                            return json.dumps({'response': 700, 'data': 'id folder already exists'})
                        else:
                            d = db.change_id_folder(item['folder_id'], item['new']['folder_id'])
                            if d == 'success':
                                return json.dumps({'response': 200, 'data': 'DB.change_folder.success'})
                            else:
                                return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})
                    return json.dumps({'response': 200, 'data': 'no changes'})
                else:
                    return json.dumps({'response': 300, 'data': 'folder not exists'})

            else:
                return self.bad_request
        except (OSError, Exception):
            return self.bad_request

    def delete(self, r, login, access):
        try:
            if r['object'] == 'HOST':
                item = r['item']

                h = db.delete_host(item)

                if h == 'success':
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''удалил хост <{item}>''')
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'not found':
                    return json.dumps({'response': 300, 'data': 'ip not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            elif r['object'] == 'FOLDER':
                item = r['item']

                h = db.delete_folder(item)

                if h == 'success':
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''удалил папку с id <{item}>''')
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'folder not exists':
                    return json.dumps({'response': 300, 'data': 'folder not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            elif r['object'] == 'USER':
                item = r['item']

                h = db.delete_user(item)

                if h == 'success':
                    self.parent.log.user_event(login, access, '0.0.0.0', f'''удалил учётную запись клиента <{item}>''')
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'folder not exists':
                    return json.dumps({'response': 300, 'data': 'user not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            elif r['object'] == 'PHONE':
                item = r['item']

                h = db.delete_phone(item)

                if h == 'success':
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'folder not exists':
                    return json.dumps({'response': 300, 'data': 'folder not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            else:
                return self.bad_request
        except (OSError, Exception):
            return self.bad_request

    def service(self, r, login, admin='guest'):
        command = r['command']
        item = r['item']

        try:
            if command == 10:
                self.parent.pinger.start_ping_all()
                self.parent.log.user_event(login, admin, '0.0.0.0', 'запустил проверку всех хостов')
                return json.dumps({'response': 200, 'data': ''})
            elif command == 20:
                if item:
                    self.parent.pinger.start_ping_one(item)
                    self.parent.log.user_event(login, admin, '0.0.0.0', f'запустил проверку одного хоста <{item}>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 21:
                self.parent.pinger.start_ping_dead()
                self.parent.log.user_event(login, admin, '0.0.0.0', 'запустил проверку недоступных хостов')
                return json.dumps({'response': 200, 'data': ''})

            elif command == 82:
                if item:
                    return json.dumps({'response': 200, 'data': self.parent.get_uptime()})
                else:
                    return self.bad_request

            elif admin != 'admin':
                return self.no_permissions()

            elif command == 30:
                self.parent.log.user_event(login, admin, '0.0.0.0', 'reboot/off server')
                sys.exit()
            elif command == 40:
                if item:
                    if db.icmp_params_update(ping_hosts_per_sec=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_per_second(int(item))
                    self.parent.log.user_event(login, admin, '0.0.0.0', 'изменил парметры проверки хостов <скорость проверки>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 50:
                if item:
                    if db.icmp_params_update(icmp_with_host=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_count(int(item))
                    self.parent.log.user_event(login, admin, '0.0.0.0',
                                   'изменил парметры проверки хостов <кол-во icmp на хост>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 60:
                if item:
                    if db.icmp_params_update(icmp_interval=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_interval(int(item))
                    self.parent.log.user_event(login, admin, '0.0.0.0', 'изменил парметры проверки хостов <интервал icmp>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 70:
                if item:
                    if db.icmp_params_update(auto_ping=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_auto_ping_interval(int(item))
                    self.parent.log.user_event(login, admin, '0.0.0.0', 'изменил парметры проверки хостов <частота проверок>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 80:
                if item:
                    if db.icmp_params_update(icmp_timeout=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_timeout(int(item))
                    self.parent.log.user_event(login, admin, '0.0.0.0', 'изменил парметры проверки хостов <icmp timeout>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 81:
                if item:
                    self.parent.disconnect_user(item)
                    self.parent.log.user_event(login, admin, '0.0.0.0', f'отключил клиента с IP: <{item}>')
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request

            else:
                self.parent.log.user_event(login, admin, '0.0.0.0', 'error, code <100> bad request')
                return self.bad_request

        except (Exception,):
            self.parent.log.user_event(login, admin, '0.0.0.0', 'error, code <100> bad request')
            return self.bad_request

    @staticmethod
    def auth_success_response():
        return json.dumps({'response': 800, 'data': 'auth success'})

    @staticmethod
    def auth_failed_response():
        return json.dumps({'response': 400, 'data': 'auth error'})

    @staticmethod
    def auth_timeout_response():
        return json.dumps({'response': 900, 'data': 'auth timeout'})

    @staticmethod
    def no_permissions():
        return json.dumps({'response': 600, 'data': 'no permissions'})


class Server(socket.socket):
    """
    Сервер основанный на сокетах с применением asyncio.
    Принимает соединения, и выполняет комманды, редактирование БД, отправляет данные из БД
    """

    clients = {} 

    def __init__(self, logger):
        """
        Инициализация сокета сервера,
        установка его в неблокирующий режим,
        для корректной работы ассинхронных сокетов

        Создание объекта класса Pinger, и запуск его работы
        """
        self.properties = self.load_properties()  # загрузка параметров из конфигурационного файла

        self._ADMIN_USER = {'login': self.properties['DefaultAdminLogin'], 'password': self.properties['DefaultAdminPassw']}
        self.PORT = int(self.properties['TcpPort'])
        self.IP = self.properties['Ip']
        self._RECV_TIMEOUT = int(self.properties['TimeoutConnection'])

        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind((self.IP, self.PORT))
        self.listen(5)
        self.setblocking(False)  # перевод сокета в неблокирующий режим
        self.loop = asyncio.get_event_loop()  # текущий EventLoop
        self.protocol = Protocol()  # простой протокол поверх TCP
        self.request_handler = RequestHandler(self)  # обработчик запросов от клиентов
        self.pinger = Pinger(*db.icmp_params(), parent_server=self)  # пингер хостов
        self.log = logger
        self.time_start_server = time.time()  # время запуска сервера
        self.temp_users_web = {}

    def get_uptime(self):
        """Получить время работы сервера"""
        n = time.time() - self.time_start_server
        time_format = str(datetime.timedelta(seconds=int(n)))
        return time_format

    @staticmethod
    def load_properties():
        try:
            def unpack(s, value):
                if value in s:
                    return s[len(value + ' = '):]

            params = {}
            with open(file='server.settings.ini', mode='r') as file:
                data = file.read().split('\n')
                for param in ('Ip', 'TcpPort', 'TimeoutConnection', 'DefaultAdminLogin', 'DefaultAdminPassw', 'HttpPort'):
                    for line in data:
                        if param in line:
                            params[param] = unpack(line, param)
                if len(params) == 6:
                    return params
                return
        except (Exception,):
            print('Ошибка инициализации сервера: проверьте конфигурационный файл сервера: server.settings.ini')
            return

    def run(self):
        # запуск сервера через метод принятия соединений от клиентов
        self.loop.create_task(self._accept_client())
        self.loop.create_task(self.watch_temp_web())

    def disconnect_user(self, ip):
        """метод отлключения пользователя по логину"""
        for sock, data in list(self.clients.items()):
            # print(sock, data)
            if data[0] == tuple(ip):
                self.close_socket(sock)

    def close_socket(self, sock, sock_addr=None, alias_login=None):
        """метод полноценного отключения клиентов от сервера"""
        if sock in self.clients:
            sock_addr, access, login = self.clients[sock]
            del self.clients[sock]
            try:
                sock.close()
            except (Exception,):
                pass
            self.log.user_event(login, access, sock_addr, msg=f'отключился от сервера {sock_addr}')  # вывод лога
            db.change_last_online(login)  # изменение даты последнего посещения сервера в БД

    async def _accept_client(self):
        while True:
            try:
                client_sock, client_addr = await self.loop.sock_accept(self)
                client_sock.setblocking(False)
            except (Exception,):
                continue
            self.loop.create_task(self.accept_client(client_sock, client_addr))

    async def accept_client(self, client_sock, client_addr):
        """принятие соединенений от клиентов"""

        auth_ = await self.auth_client(client_sock)
        if auth_[0] == 'guest':
            # если зашёл обычный пользователь
            self.clients[client_sock] = (client_addr, 'guest', auth_[1])
            self.loop.create_task(self.recv_client(client_sock, client_addr, login=auth_[1]))  # запуск приёма байт от клиента
            self.log.user_event(auth_[1], 'guest', client_addr, f'подключился к серверу {client_addr}')  # вывод лога
            await self.protocol.send_all(client_sock, self.request_handler.auth_success_response())
        elif auth_[0] == 'admin':
            # если зашел админ
            self.clients[client_sock] = (client_addr, 'admin', auth_[1])
            self.loop.create_task(self.recv_client(client_sock, client_addr, auth_[1], 'admin'))
            self.log.user_event(auth_[1], 'admin', client_addr, f'подключился к серверу {client_addr}')  # вывод лога
            await self.protocol.send_all(client_sock, self.request_handler.auth_success_response())
        else:
            # если неверный логин и пароль или сам запрос
            if auth_[0] == 'timeout':
                await self.protocol.send_all(client_sock, self.request_handler.auth_timeout_response())
                self.log.alarm(f'Отклонена попытка подключения с адреса {client_addr} <connection timeout>')
            elif auth_[0] == 'login/passw':
                await self.protocol.send_all(client_sock, self.request_handler.auth_failed_response())
                self.log.alarm(f'С адреса {client_addr} клиент с логином [{auth_[1]}] ввёл неверный пароль')
            else:
                await self.protocol.send_all(client_sock, self.request_handler.auth_failed_response())
                self.log.alarm(f'Отклонена попытка подключения с адреса {client_addr} <flood запрос>')
            client_sock.close()

    async def auth_client(self, sock):
        """авторизация клиентов
        и отключение в случае если не приходит запросов"""
        try:
            auth = await asyncio.wait_for(self.protocol.recv(sock), timeout=15)
            data = json.loads(auth)  # декодирование json строки в объект python
            for user in db.registered_users():
                if data == {'login': user[0], 'password': user[1]}:
                    if user[2] == 'guest' or user[2] == 'admin':
                        # self._alias_connected_login(user[0])
                        return user[2], user[0]
                    else:
                        return None, None
                elif data == self._ADMIN_USER:
                    # self._alias_connected_login(self._ADMIN_USER['login'])
                    return 'admin', self._ADMIN_USER['login']
                elif data['login'] == user[0]:
                    return 'login/passw', user[0]
                elif data['login'] == self._ADMIN_USER['login']:
                    return 'login/passw', self._ADMIN_USER['login']
            return None, None
        except asyncio.exceptions.TimeoutError:
            return 'timeout', None
        except (Exception,):
            return None, None

    def _alias_connected_login(self, login_new_connect):
        """отключение подключенного к серверу пользователя,
        если он пытается авторизоваться не закрыв текущую сессию"""
        for client, data in list(self.clients.items()):
            login = data[2]
            if login == login_new_connect:
                self.close_socket(client)

    async def recv_client(self, client_sock, client_addr, login, access='guest'):
        # приняетие байтов данных от клиента
        if access == 'admin':
            admin = True
        else:
            admin = False
        while True:
            data = await self.protocol.recv(client_sock)
            if not data:
                self.close_socket(client_sock, client_addr)
                break
            response = self.request_handler.handler(data.decode('utf-8'), login, access)
            await self.protocol.send_all(client_sock, response)

    def broadcast_send(self, msg):
        """Отправка сообщения всем подключенным клиентам"""
        for sock in self.clients:
            self.loop.create_task(self.protocol.send_all(sock, msg))

    def current_event_loop(self):
        return self.loop

    async def loop_timer_web(self, login_web):
        """жалкое подобие удержания сессии"""
        while True:
            await asyncio.sleep(2)
            if not self.temp_users_web.get(login_web):
                del self.temp_users_web[login_web]
                self.log.alarm(f'Web-session, сессия пользователя <{login_web}> разорвана из-за бездействия.')
                break
            if login_web in self.temp_users_web:
                timer = self.temp_users_web.get(login_web)
                if timer > 0:
                    timer -= 2
                    self.temp_users_web[login_web] = timer
                else:
                    del self.temp_users_web[login_web]

    async def watch_temp_web(self):
        """с переодичностью 5 мин выводит кол-во http сессий"""
        while True:
            await asyncio.sleep(60 * 5)
            if self.temp_users_web:
                logins = ''
                for i in self.temp_users_web.keys():
                    logins += i + ', '
                self.log.alarm(f'[Web] На сервере установлено <{len(self.temp_users_web)}>'
                          f' HTTP соединение: {logins[:-2]}')


# if __name__ == '__main__':
#     # основной TCP сервер (для доступа из десктопной программы)
#     server = Server()
#     server.run()

#     # Web сервер (для удобного просмотра с телефона)
#     web_server = AsyncHTTPServer(server.IP, 443, HTTPRequestHandler)

#     # Простой логер событий на сервере
#     log = Logger(server)

#     event_loop = asyncio.get_event_loop()
#     event_loop.create_task(web_server.run_server())
#     try:
#         loop = event_loop.run_forever()
#     except KeyboardInterrupt:
#         sys.exit(0)
