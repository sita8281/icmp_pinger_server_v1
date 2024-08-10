import json
import base64
import os
from micro_async_http.http_server import AsyncSimpleHTTPRequestHandler
import db


class HTTPRequestHandler(AsyncSimpleHTTPRequestHandler):

    def __init__(self, request, sock, sock_addr, *args, **kwargs):
        super().__init__(request, sock, sock_addr)

        self.stream_server = kwargs.get('stream_server')

        self.user_login = ''
        self.user_access = ''

        self.allowed_paths = (
            'web/',  # доступ ко всей папке
            'hosts.db',
            'logs.txt',
        )

        self.api_routes = (
            ('/api/check_all', self.check_ALL),
            ('/api/check_dead', self.check_DEAD),
            ('/api/hosts/all', self.hosts_ALL),
            ('/api/hosts/dead', self.hosts_DEAD),
            ('/api/hosts/live', self.hosts_LIVE),
            ('/api/hosts/pause', self.hosts_PAUSE),
        )

    def check_ALL(self):
        """потокобезопастный вызов в цикле asyncio пинга"""
        self.stream_server.pinger.start_ping_all()
        self.send_response_json('Ping checking ALL started...')
        self.stream_server.log.user_event(self.user_login, self.user_access, '', '[Web] запустил проверку всех хостов')

    def check_DEAD(self):
        """потокобезопастный вызов в цикле asyncio пинга"""
        self.stream_server.pinger.start_ping_dead()
        self.send_response_json('Ping checking DEAD started...')

        self.stream_server.log.user_event(self.user_login, self.user_access, '', '[Web] запустил проверку недоступных хостов')

    def hosts_ALL(self):
        """отправить из БД список всех хостов"""
        self.send_response_json(db.all_info())

    def hosts_DEAD(self):
        """отправить из БД список мертвых хостов"""
        hosts = []
        for host in db.all_info():
            if host[3] == 'clock.offline' or host[3] == 'offline':
                hosts.append(host)
        self.send_response_json(hosts)

    def hosts_LIVE(self):
        """отправить из БД список живых хостов"""
        hosts = []
        for host in db.all_info():
            if host[3] == 'clock.online' or host[3] == 'online':
                hosts.append(host)
        self.send_response_json(hosts)

    def hosts_PAUSE(self):
        """отправить из БД список хостов на паузе"""
        hosts = []
        for host in db.all_info():
            if host[3] == 'pause':
                hosts.append(host)
        self.send_response_json(hosts)

    def send_response_json(self, obj):
        """отправка response 200, c JSON строкой"""
        json_obj = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Lenght', str(len(json_obj)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Server', self.server_name)
        self.send_header('Date', self.date)
        self.end_headers()
        self.send_data(json_obj)

    def is_authorized(self):
        """Проверка авторизации"""
        auth_header = self.headers.get('Authorization')
        if not auth_header:
            self.send_error(401)  # response Not Authorized
        else:
            for user in db.registered_users():
                login = user[0]
                passw = user[1]
                self.user_login = user[0]
                self.user_access = user[2]
                encoded_string = base64.b64encode(f'{login}:{passw}'.encode('utf-8')).decode('ascii')
                if auth_header == f'Basic {encoded_string}':
                    # пользователь авторизовался
                    if login in self.stream_server.temp_users_web:
                        self.stream_server.temp_users_web[login] = 60 * 15  # через сколько сек. завершать условную сессию
                    else:
                        self.stream_server.temp_users_web[login] = 60 * 15
                        self.loop.create_task(self.stream_server.loop_timer_web(login))
                        self.stream_server.log.user_event(login=login,
                                       access=user[2],
                                       ip='',
                                       msg=f'[Web] подключился к серверу {self.client_address}')

                        # изменение даты последнего посещения в БД
                        db.change_last_online(login)

                    return True
            self.send_error(401)  # response Not Authorized

    def access_file(self):
        try:
            path = self.path.split('?')[0].replace('/', '', 1)
            if os.path.exists(path):
                if path in self.allowed_paths:
                    return path
                elif len(path.split('/')) >= 2 and path[-1] != '/':
                    return path
                elif len(path.split('/')) >= 2 and path[-1] == '/':
                    self.send_error(404)
                else:
                    self.send_error(403)
            else:
                self.send_error(404)
        except (OSError, Exception):
            self.send_error(500)

    def access_api(self):

        if '/api' in self.path:
            for path, method in self.api_routes:
                if self.path.split('?')[0] == path:
                    method()
                    return True
            self.send_error(404)

    def do_FOUND(self, redirect_path):
        self.send_response(302, msg='Found')
        self.send_header('Location', redirect_path)
        self.send_header('Date', self.date)
        self.send_header('Server', self.server_name)
        self.end_headers()

    async def do_GET(self):

        # проверка авторизации
        if not self.is_authorized():
            return

        # выход из учётной записи
        if self.path == '/logout':
            self.send_error(401)
            return

        # проверка доступа к API методу и его вызов
        if self.access_api():
            return

        # redirect на главную страницу
        if self.path == '/':
            self.do_FOUND('/web/index.html')
            return

        # проверка доступа к файлу и его отправка
        path_f = self.access_file()
        if path_f:
            await self.send_file(path=path_f)
            return

        self.send_response(200)