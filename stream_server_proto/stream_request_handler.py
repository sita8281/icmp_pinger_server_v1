import json
import db
import time
import sys


class RequestHandler:
    """
    Обработчик запросов от клиентов
    Основная суть состоит в обработке запроса и отправки ответа на него
    В основном вся логика построена вокруг БД
    """
    requests = ['GET', 'POST', 'PUT', 'DELETE', 'SERVICE']
    objects = ['FOLDER', 'HOST', 'USER']
    bad_request = json.dumps({'response': 100, 'data': 'bad request'})

    def __init__(self):
        self.parent = None
    
    def set_parent_server(self, parent):
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