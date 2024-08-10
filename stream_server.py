import socket
import time
import asyncio
import json
import datetime
import db


class Server(socket.socket):
    """
    Сервер основанный на сокетах с применением asyncio.
    Принимает соединения, и выполняет комманды, редактирование БД, отправляет данные из БД
    """

    clients = {} 

    def __init__(self, logger, proto, handler, pinger):
        """
        Инициализация сокета сервера,
        установка его в неблокирующий режим,
        для корректной работы ассинхронных сокетов

        Создание объекта класса Pinger, и запуск его работы
        """
        self.log = logger
        self.log.set_callback_broadcast(self.broadcast_send)
        self.protocol = proto  # поверх TCP
        self.request_handler = handler  # обработчик
        self.request_handler.set_parent_server(self) # передача сервера в обработчик
        self.pinger = pinger  # pinger объект
        self.pinger.set_parent_server(self)
        self.pinger.set_icmp_params(*db.icmp_params())
        self.pinger.run_ping_loop()
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
