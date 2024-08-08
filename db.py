import sqlite3
import time
import base64


def init_db():
    # подлкючение к базе данных и создание курсора

    try:
        base = sqlite3.connect('hosts.db')
        cursor = base.cursor()
        return base, cursor
    except Exception:
        # если не удалось, вернет 'connect error'
        return 'connect error'


def icmp_params():
    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM icmp_params''').fetchall()
    a, b, c, d, f, _ = r[0]
    base.close()
    return a, b, c, d, f


def icmp_params_update(auto_ping=None,
                       icmp_with_host=None,
                       icmp_interval=None,
                       ping_hosts_per_sec=None,
                       icmp_timeout=None):
    # поменять параметры пинга
    base, cursor = init_db()
    try:
        if auto_ping:
            cursor.execute(f'''UPDATE icmp_params SET auto_ping == ? WHERE icmp == ?''',
                           (auto_ping, 'parametrs',))

        if icmp_with_host:
            cursor.execute(f'''UPDATE icmp_params SET icmp_with_host == ? WHERE icmp == ?''',
                           (icmp_with_host, 'parametrs',))

        if icmp_interval:
            cursor.execute(f'''UPDATE icmp_params SET icmp_interval == ? WHERE icmp == ?''',
                           (icmp_interval, 'parametrs',))

        if ping_hosts_per_sec:
            cursor.execute(f'''UPDATE icmp_params SET ping_hosts_per_sec == ? WHERE icmp == ?''',
                           (ping_hosts_per_sec, 'parametrs',))

        if icmp_timeout:
            cursor.execute(f'''UPDATE icmp_params SET icmp_timeout == ? WHERE icmp == ?''',
                           (icmp_timeout, 'parametrs',))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def insert_host(ip, name, folder_id, state, time, info, sms):
    # добавить новый хост в базу данных

    base, cursor = init_db()  # подкл. к базе
    try:
        cursor.execute('''INSERT INTO servers VALUES(?, ?, ?, ?, ?, ?, ?)''', (ip, name, folder_id, state, time, info, sms))
        base.commit()
    except sqlite3.IntegrityError:
        # исключение если пытаются добавить уже существующий хост
        base.close()
        return 'unique item error'
    except Exception:
        base.close()
        return 'unknown error'

    base.close()
    return 'success'


def delete_host(ip_id):
    # удалить хост из базы данных

    base, cursor = init_db()
    try:
        cursor.execute('''DELETE FROM servers WHERE ip == ?''', (ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение при возникновении ошибки
        return 'unknown error'
    base.close()
    return 'success'


def change_folder(ip_id, data, search_folder=False):
    # поменять папку в которой находится хост

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET folder == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_name(ip_id, data):
    # поменять имя хоста

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET name == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_ip(ip_id, data):
    # поменять ip хоста

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET ip == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_state(ip_id, data):
    # поменять значение стоит на паузе хост или нет

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET state == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_sms(ip_id, sms_state):
    # поменять значение рассылать SMS или нет

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET send_sms == ? WHERE ip == ?''', (sms_state, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_time(ip_id, data):
    # поменять время последнего изменения

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET time == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_info(ip_id, data):
    # инфа о хосте

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE servers SET info == ? WHERE ip == ?''', (data, ip_id,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def all_info():
    # получить список всех хостов в базе
    # вернёт List

    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM servers ''').fetchall()
    base.close()
    return r


def registered_users():
    # получить список всех пользователей в базе
    # вернёт List

    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM users ''').fetchall()
    users = []
    for user in r:
        _login = base64.b64decode(user[0]).decode('utf-8')
        _passw = base64.b64decode(user[1]).decode('utf-8')
        users.append((_login, _passw, user[2], user[3]))
    base.close()
    return users


def phone_numbers():
    # получить список всех номеров SMS рассылки в базе
    # вернёт List

    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM phones ''').fetchall()
    base.close()
    return r


def sms_api():
    # получить список всех номеров SMS рассылки в базе
    # вернёт List

    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM phones ''').fetchall()
    base.close()
    return r


def one_info(ip_id):
    # получить всю информацию о хосте по IP
    # если хост не найден, то вернёт 'not found'

    base, cursor = init_db()
    try:
        recv = cursor.execute('''SELECT * FROM servers WHERE ip == ?''', (ip_id,)).fetchone()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    if recv:
        base.close()
        return recv
    else:
        base.close()
        return 'not found'


def create_folder(id_folder, name_folder):
    # создать новую папку в базе

    base, cursor = init_db()
    try:
        cursor.execute('''INSERT INTO folders VALUES(?, ?)''', (id_folder, name_folder))
    except sqlite3.IntegrityError:
        # исключение если пытаются добавить уже существующую папку
        base.close()
        return 'unique item error'
    except Exception:
        base.close()
        return 'unknown error'
    base.commit()
    return 'success'


def create_user(login, passw, access):
    # создать нового пользователя

    base, cursor = init_db()
    try:
        encoded_login = base64.b64encode(login.encode('utf-8')).decode('ascii')
        encoded_passw = base64.b64encode(passw.encode('utf-8')).decode('ascii')
        cursor.execute('''INSERT INTO users VALUES(?, ?, ?, ?)''', (encoded_login, encoded_passw, access, None))
    except sqlite3.IntegrityError:
        # исключение если пытаются добавить уже существующую папку
        base.close()
        return 'unique item error'
    except Exception:
        base.close()
        return 'unknown error'
    base.commit()
    return 'success'


def create_phone_number(number, info):
    # добавить новый номер в базу

    base, cursor = init_db()
    try:
        cursor.execute('''INSERT INTO phones VALUES(?, ?)''', (number, info))
    except sqlite3.IntegrityError:
        # исключение если пытаются добавить уже существующую папку
        base.close()
        return 'unique item error'
    except Exception:
        base.close()
        return 'unknown error'
    base.commit()
    return 'success'


def delete_folder(id_folder):
    # удалить папку из базы данных

    base, cursor = init_db()
    try:
        if check_folder(cursor, id_folder):
            cursor.execute('''DELETE FROM folders WHERE id == ?''', (id_folder,))
            base.commit()
        else:
            base.close()
            return 'folder not exists'
    except Exception:
        base.close()
        # исключение при возникновении ошибки
        return 'unknown error'
    base.close()
    return 'success'


def delete_user(login):
    # удалить пользователя из базы данных

    base, cursor = init_db()
    try:
        login = base64.b64encode(login.encode('utf-8')).decode('ascii')
        cursor.execute('''DELETE FROM users WHERE login == ?''', (login,))
        base.commit()
    except Exception:
        base.close()
        # исключение при возникновении ошибки
        return 'unknown error'
    base.close()
    return 'success'


def delete_phone(number):
    # удалить телефон из базы данных

    base, cursor = init_db()
    try:
        cursor.execute('''DELETE FROM phones WHERE number == ?''', (number,))
        base.commit()
    except Exception:
        base.close()
        # исключение при возникновении ошибки
        return 'unknown error'
    base.close()
    return 'success'


def change_id_folder(id_folder, new_id):
    # переименовать папку

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE folders SET id == ? WHERE id == ?''', (new_id, id_folder,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def change_name_folder(id_folder, new_name):
    # переименовать папку

    base, cursor = init_db()
    try:
        cursor.execute(f'''UPDATE folders SET name == ? WHERE id == ?''', (new_name, id_folder,))
        base.commit()
    except Exception:
        base.close()
        # исключение если возникла ошибка
        return 'unknown error'
    base.close()
    return 'success'


def load_folders():
    # получить все папки из базы данных

    base, cursor = init_db()
    r = cursor.execute('''SELECT * FROM folders ''').fetchall()
    base.close()
    return r


def check_folder(cursor, id_folder):
    # проверить есть ли папка в базе

    res = cursor.execute('SELECT * FROM folders WHERE id=?', (id_folder,))
    if res.fetchone() is None:
        return False
    else:
        return True


def check_folder_(id_folder):
    # проверить есть ли папка в базе

    base, cursor = init_db()
    res = cursor.execute('SELECT * FROM folders WHERE id=?', (id_folder,))
    if res.fetchone() is None:
        return False
    else:
        return True


def change_folder_all_hosts(id_folder, new_id):
    # поменять папку на хостах

    for i in all_info():
        if i[2] == id_folder:
            change_folder(i[0], new_id)


def change_last_online(login):
    base, cursor = init_db()
    try:
        login = base64.b64encode(login.encode('utf-8')).decode('ascii')
        cursor.execute('''UPDATE users SET last_online == ? WHERE login == ?''', (int(time.time()), login))
    except sqlite3.IntegrityError:
        # исключение если пытаются добавить уже существующую папку
        base.close()
        return 'unique item error'
    except Exception:
        base.close()
        return 'unknown error'
    base.commit()
    return 'success'
