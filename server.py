import socket
import sys
import time
import asyncio
import json
from datetime import datetime
import struct
import db
from icmplib import async_ping
import zlib


class SmsSender:
    """
    Класс оповещателя об отключении или включении хоста
    """
    pass


class Logger:
    """
    Простой логер событий.

    Типы событий:
    11 - клиент зашёл
    12 - клиент вышел
    13 - админ зашёл
    14 - админ вышел

    20 - пинг на хост запущен
    21 - пинг пройден успешно
    22 - пинг не пройден
    """
    def __init__(self, srv):
        self.log1 = []  # лог
        self.server = srv

    def append(self, code, info):
        self.log1.append([time.time(), code, info])
        t = datetime.now()
        msg = json.dumps({'response': 33, 'data': f'{t.day}/{t.month}/{t.year} {t.hour}:{t.minute}:{t.second} + {info}'})
        self.server.broadcast_send(msg)
        print(f'{t.day}/{t.month}/{t.year} {t.hour}:{t.minute}:{t.second}' +
              f'   ' + info)
        if len(self.log1) > 20:
            self.log1.pop(0)

    @property
    def get_log(self):
        return self.log1


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

    def __init__(self, auto_ping, icmp_with_host, icmp_interval, ping_hosts_per_sec, icmp_timeout):
        self._AUTO_PING_INTERVAL = auto_ping
        self._ICMP_COUNT = icmp_with_host
        self._ICMP_INTERVAL = icmp_interval
        self._ICMP_PER_SECOND = ping_hosts_per_sec
        self._ICMP_TIMEOUT = icmp_timeout

        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._run_auto_ping())

    async def _icmp_ping_host(self, ip):
        try:
            host = await async_ping(ip,
                                    count=self._ICMP_COUNT,
                                    interval=self._ICMP_INTERVAL,
                                    timeout=self._ICMP_TIMEOUT)

            current_time = int(time.time())

            if host.is_alive:
                # если хост ответил на icmp
                log.append(code=21,
                           info=f'Хост <{ip}> доступен. '
                                f'(Принято пакетов {host.packets_received} из {host.packets_sent})')
                if db.one_info(ip)[3] == 'offline':
                    db.change_time(ip, current_time)
                    db.change_state(ip, 'online')

            else:
                # если хост не ответил на icmp
                log.append(code=22,
                           info=f'Хост <{ip}> не доступен.'
                                f' (Принято пакетов {host.packets_received} из {host.packets_sent})')
                if db.one_info(ip)[3] == 'online':
                    db.change_time(ip, current_time)
                    db.change_state(ip, 'offline')
        except (Exception,):
            return

    async def _ping_all(self):
        # пинг всех хостов в БД
        all_hosts = db.all_info()
        log.append(code=20, info='Запуск проверки всех хостов по расписанию...')
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
            self.start_ping_all()
            await asyncio.sleep(self._AUTO_PING_INTERVAL)  # интервал итараций цикла

    def start_ping_all(self):
        self.loop.create_task(self._ping_all())

    def start_ping_one(self, ip):
        self.loop.create_task(self._ping_one(ip))

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

    def handler(self, request, admin=None):
        try:
            req = json.loads(request)
            type_req = req['request']
            if type_req in self.requests:
                if type_req == 'GET':
                    return self.get(req)
                elif type_req == 'POST':
                    if admin:
                        return self.post(req)
                    else:
                        return self.no_permissions()
                elif type_req == 'PUT':
                    if admin:
                        return self.put(req)
                    else:
                        return self.no_permissions()
                elif type_req == 'DELETE':
                    if admin:
                        return self.delete(req)
                    else:
                        return self.no_permissions()
                elif type_req == 'SERVICE':
                    return self.service(req, admin)
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
                        if host[3] == 'offline':
                            dead_hosts.append(host)
                    return json.dumps({'response': 200, 'data': dead_hosts})

                elif item == 'live':
                    live_hosts = []
                    hosts = db.all_info()
                    for host in hosts:
                        if host[3] == 'online':
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
                        return json.dumps({'response': 200, 'data': users})
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
            else:
                return self.bad_request
        except (OSError, Exception):
            return self.bad_request

    def post(self, r):
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
                    item['sms']
                )

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.host exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                else:
                    return json.dumps({'response': 200, 'data': 'DB.success'})

            elif r['object'] == 'FOLDER':
                item = r['item']
                d = db.create_folder(
                    str(max([int(i[0]) for i in db.load_folders()]) + 1),  # генерация уникального id
                    item['name']
                )

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.folder exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                elif d == 'success':
                    return json.dumps({'response': 200, 'data': 'DB.success'})

            elif r['object'] == 'USER':
                item = r['item']
                d = db.create_user(item['login'], item['passw'], item['access'])

                if d == 'unique item error':
                    return json.dumps({'response': 700, 'data': 'DB.user exists'})
                elif d == 'unknown error':
                    return json.dumps({'response': 500, 'data': 'DB.error'})
                elif d == 'success':
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

    def put(self, r):
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

                    if item['new']['folder_id']:
                        result = db.change_folder(item['ip'], item['new']['folder_id'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_folder.error'})

                    if item['new']['state']:
                        result = db.change_state(item['ip'], item['new']['state'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_state.error'})

                    if item['new']['info']:
                        result = db.change_info(item['ip'], item['new']['info'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_info.error'})

                    if item['new']['sms']:
                        result = db.change_sms(item['ip'], item['new']['sms'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_sms.error'})

                    if item['new']['ip']:
                        result = db.change_ip(item['ip'], item['new']['ip'])
                        if not result == 'success':
                            return json.dumps({'response': 500, 'data': 'DB.change_ip.error'})

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

    def delete(self, r):
        try:
            if r['object'] == 'HOST':
                item = r['item']

                h = db.delete_host(item)

                if h == 'success':
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'not found':
                    return json.dumps({'response': 300, 'data': 'ip not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            elif r['object'] == 'FOLDER':
                item = r['item']

                h = db.delete_folder(item)

                if h == 'success':
                    return json.dumps({'response': 200, 'data': 'DB.delete.success'})
                elif h == 'folder not exists':
                    return json.dumps({'response': 300, 'data': 'folder not exists'})
                else:
                    return json.dumps({'response': 500, 'data': 'DB.error'})

            elif r['object'] == 'USER':
                item = r['item']

                h = db.delete_user(item)

                if h == 'success':
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

    def service(self, r, admin=None):
        command = r['command']
        item = r['item']

        try:
            if command == 10:
                self.parent.pinger.start_ping_all()
                return json.dumps({'response': 200, 'data': ''})
            elif command == 20:
                if item:
                    self.parent.pinger.start_ping_one(item)
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif not admin:
                return self.no_permissions()
            elif command == 30:
                sys.exit()
            elif command == 40:
                if item:
                    if db.icmp_params_update(ping_hosts_per_sec=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_per_second(int(item))
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 50:
                if item:
                    if db.icmp_params_update(icmp_with_host=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_count(int(item))
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 60:
                if item:
                    if db.icmp_params_update(icmp_interval=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_interval(int(item))
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 70:
                if item:
                    if db.icmp_params_update(auto_ping=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_auto_ping_interval(int(item))
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request
            elif command == 80:
                if item:
                    if db.icmp_params_update(icmp_timeout=int(item)) != 'success':
                        return json.dumps({'response': 500, 'data': 'DB.error'})
                    self.parent.pinger.set_icmp_timeout(int(item))
                    return json.dumps({'response': 200, 'data': ''})
                else:
                    return self.bad_request

            elif command == 90:
                return json.dumps({'response': 200, 'data': log.get_log})

            else:
                return self.bad_request

        except (Exception,):
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

    def __init__(self):
        """
        Инициализация сокета сервера,
        установка его в неблокирующий режим,
        для корректной работы ассинхронных сокетов

        Создание объекта класса Pinger, и запуск его работы
        """
        properties = self.load_properties()  # загрузка параметров из конфигурационного файла

        self._ADMIN_USER = {'login': properties['DefaultAdminLogin'], 'password': properties['DefaultAdminPassw']}
        self._PORT = int(properties['TcpPort'])
        self._IP = properties['Ip']
        self._RECV_TIMEOUT = int(properties['TimeoutConnection'])

        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind((self._IP, self._PORT))
        self.listen(5)
        self.setblocking(False)  # перевод сокета в неблокирующий режим
        self.loop = asyncio.get_event_loop()  # текущий EventLoop
        self.protocol = Protocol()  # простой протокол поверх TCP
        self.request_handler = RequestHandler(self)  # обработчик запросов от клиентов
        self.pinger = Pinger(*db.icmp_params())  # пингер хостов

    @staticmethod
    def load_properties():
        try:
            def unpack(s, value):
                if value in s:
                    return s[len(value + ' = '):]

            params = {}
            with open(file='server.settings.ini', mode='r') as file:
                data = file.read().split('\n')
                for param in ('Ip', 'TcpPort', 'TimeoutConnection', 'DefaultAdminLogin', 'DefaultAdminPassw'):
                    for line in data:
                        if param in line:
                            params[param] = unpack(line, param)
                if len(params) == 5:
                    return params
                return
        except (Exception,):
            print('Ошибка инициализации сервера: проверьте конфигурационный файл сервера: server.settings.ini')
            return

    def run(self):
        # запуск сервера через метод принятия соединений от клиентов
        self.loop.create_task(self._accept_client())

    def close_socket(self, sock, sock_addr=None):
        # метод отключения сокетов клиентов
        if sock in self.clients:
            sock_addr, access = self.clients[sock]
            if access == 'admin':
                s = 'Администратор'
                code = 14
            else:
                s = 'Клиент'
                code = 12
            del self.clients[sock]
            try:
                sock.close()
            except (Exception,):
                pass
            log.append(code, info=f'{s} отключился от сервера {sock_addr}')

    async def _accept_client(self):
        while True:
            try:
                client_sock, client_addr = await self.loop.sock_accept(self)
                client_sock.setblocking(False)
            except (Exception,):
                continue
            self.loop.create_task(self.accept_client(client_sock, client_addr))

    async def accept_client(self, client_sock, client_addr):
        # принятие соединенений от клиентов

        self.clients[client_sock] = None  # добавление подключившегося клиента в список

        auth_ = await self.auth_client(client_sock)
        if auth_ == 'guest':
            # если зашёл обычный пользователь
            self.clients[client_sock] = (client_addr, 'guest')
            self.loop.create_task(self.recv_client(client_sock, client_addr))  # запуск приёма байт от клиента
            log.append(code=11, info=f'Клиент подключился к серверу {client_addr}')  # вывод лога
            await self.protocol.send_all(client_sock, self.request_handler.auth_success_response())
        elif auth_ == 'admin':
            # если зашел админ
            self.clients[client_sock] = (client_addr, 'admin')
            self.loop.create_task(self.recv_client(client_sock, client_addr, 'admin'))
            log.append(code=13, info=f'Администратор подключился к серверу {client_addr}')  # вывод лога
            await self.protocol.send_all(client_sock, self.request_handler.auth_success_response())
        else:
            # если неверный логин и пароль или сам запрос
            if auth_ == 'timeout':
                await self.protocol.send_all(client_sock, self.request_handler.auth_timeout_response())
            else:
                await self.protocol.send_all(client_sock, self.request_handler.auth_failed_response())
            client_sock.close()
            del self.clients[client_sock]

    async def auth_client(self, sock):
        # авторизация клиентов
        # и отключение в случае если не приходит запросов
        try:
            auth = await asyncio.wait_for(self.protocol.recv(sock), timeout=5)
            data = json.loads(auth)  # декодирование json строки в объект python
            for user in db.registered_users():
                if data == {'login': user[0], 'password': user[1]}:
                    if user[2] == 'guest' or user[2] == 'admin':
                        return user[2]
                    else:
                        return
                elif data == self._ADMIN_USER:
                    return 'admin'
            return
        except asyncio.exceptions.TimeoutError:
            return 'timeout'
        except (Exception,):
            return

    async def recv_client(self, client_sock, client_addr, access='guest'):
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
            response = self.request_handler.handler(data.decode('utf-8'), admin)
            await self.protocol.send_all(client_sock, response)

    def broadcast_send(self, msg):
        """Отправка сообщения всем подключенным клиентам"""
        for sock in self.clients:
            self.loop.create_task(self.protocol.send_all(sock, msg))


if __name__ == '__main__':
    # ping = Pinger()
    server = Server()
    log = Logger(server)  # логер сервера
    server.run()
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        asyncio.get_event_loop().stop()
        asyncio.get_event_loop().close()
