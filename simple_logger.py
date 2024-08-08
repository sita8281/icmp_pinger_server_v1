import json
import datetime


class Logger:
    """
    Простой логер событий.
    """
    def __init__(self, file_path: str):
        self._file_path = file_path
    
    def set_callback_broadcast(self, func: callable):
        self._broadcast_callback = func

    def alarm(self, msg):
        """предупреждения, ошибки, флуды"""
        evnt = {
            'type': 'alarm',
            'message': msg
        }
        self._send(evnt)
        self._write_logfile(msg)

    def icmp_bad(self, host):
        """хост не доступен"""
        evnt = {
            'type': 'icmp',
            'ip': host[0],
            'name': host[1],
            'state': False
        }
        self._send(evnt)

    def icmp_good(self, host):
        """пинг пройден успешно"""
        evnt = {
            'type': 'icmp',
            'ip': host[0],
            'name': host[1],
            'state': True
        }
        self._send(evnt)

    def user_event(self, login, access, ip, msg):
        """отображение действий пользователей"""
        evnt = {
            'type': 'user',
            'ip': ip,
            'login': login,
            'message': msg,
            'access': access
        }
        self._send(evnt)
        self._write_logfile(f'{login}: {msg}')

    def change_state(self, msg):
        self._write_logfile(msg)

    def _send(self, obj):
        """разослать лог"""
        msg = json.dumps(
            {'response': 33, 'data': obj})
        self._broadcast_callback(msg)

    def _write_logfile(self, msg):
        with open(file=self._file_path, mode='a', encoding='utf-8') as file:
            time_log = datetime.datetime.now().strftime('%Y/%m/%d  %H:%M:%S')
            file.write(f'[{time_log}]  {msg}\n')