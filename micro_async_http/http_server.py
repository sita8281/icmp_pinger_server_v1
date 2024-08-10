import asyncio
import time
import mimetypes
import os
import datetime
import ssl


class ErrorsHTTP:
    NOT_FOUND = """<title>404 Not Found</title>
    <h1>404 Not Found</h1>
    Файл не найден на сервере, или к нему нет доступа.
    """

    BAD_REQUEST = """<title>400 Bad Request</title>
    <h1>400 Bad Request</h1>
    Сервер не распознал текущий запрос.
    """

    UNAUTHORIZED = """<title>401 Not Authorized</title>
    <h1>401 Not Authorized</h1>
    Для продолжения требуется авторизация на сервере.
    """

    INTERNAL_ERROR = """<title>500 Internal Server Error</title>
    <h1>500 Internal Server Error</h1>
    Внутренняя ошибка сервера, запрос не удалось обработать
    """

    FORBIDDEN = """<title>403 Forbidden</title>
    <h1>403 Forbidden</h1>
    Доступ запрещён.
    """


class AsyncSimpleHTTPRequestHandler:
    """Базовый обработчик Http запросов

    поддерживаемые ошибки:
    400 - bad request
    500 - internal server error

    """
    def __init__(self, request, reader, writer, bad_request=None):
        self._reader = reader
        self._writer = writer
        self.client_address = writer.get_extra_info('peername')
        self.loop = asyncio.get_event_loop()
        self.request = request
        self.bad_request = bad_request
        self.http_errors = ErrorsHTTP()
        self.server_name = 'Deil Eye, Web Server 0.01'
        self.path = ''
        self.headers = {}
        self.wfile = b''
        self.date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

    async def handle_request(self):
        """этот метод вызывается сервером"""
        try:
            if self.bad_request:
                pass
            elif self.parse_headers():
                await self.do_GET()
            else:
                self.send_error(400)
        except Exception:
            self.send_error(500)

        self._writer.write(self.wfile)
        await self._writer.drain()

    def parse_headers(self):
        """парсинг и валидация заголовка http"""
        req_lines = self.request.split(b'\r\n')
        one_head = req_lines[0].split(b' ')
        if len(one_head) != 3:
            return
        if one_head[0] != b'GET' or one_head[2] != b'HTTP/1.1':
            return
        if one_head[1][0] != 47:  # 47 это '/' в ascii
            return
        try:
            self.path = one_head[1].decode('utf-8')

            for line in req_lines[1:]:

                params = line.decode('utf-8').split(':', 1)
                if len(params) == 2:
                    if params[1][0] == ' ':
                        normal_param = params[1].replace(' ', '', 1)
                        self.headers[params[0]] = normal_param
                    else:
                        self.headers[params[0]] = params[1]
        except UnicodeDecodeError:
            return

        return True

    async def send_file(self, path=None):
        if not path:
            path = self.path
        path = path.split('?')[0]
        file_type = mimetypes.guess_type(path)[0]
        if file_type == 'text/x-python':
            file_type = 'text/plain'
        elif not file_type:
            file_type = 'application/octet-stream'
        if path[0] == '/':
            path = path.replace('/', '', 1)

        f = await self.loop.run_in_executor(None, self._get_file, path)
        if f:
            lenght = len(f[0])
            encoding_type = ''
            self.send_response(200)
            if 'image' in file_type:
                self.send_header('Cache-Control', 'max-age=259200')
            else:
                self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Length', str(lenght))
            if file_type == 'text/plain' or file_type == 'text/html':
                encoding_type = '; charset=utf-8'
            self.send_header('Content-Type', f'{file_type}{encoding_type}')
            self.send_header('Date', self.date)
            self.send_header('Last-Modified', f[1])
            self.send_header('Server', self.server_name)
            self.end_headers()
            self.send_data(f[0])
        else:
            self.send_error(404)

    @staticmethod
    def _get_file(path):
        try:
            with open(file=path, mode='rb') as file:
                data = file.read()
                ts = os.path.getmtime(path)
                last_modify = datetime.datetime.utcfromtimestamp(ts).strftime('%a, %d %b %Y %H:%M:%S GMT')
                return data, last_modify
        except OSError:
            return

    def send_header(self, header, data):
        h = header + ': ' + data + '\r\n'
        self.wfile += bytes(h, 'utf-8')

    def end_headers(self):
        self.wfile += '\r\n'.encode('utf-8')

    def send_data(self, data):
        self.wfile += data

    def send_response(self, status, msg=''):
        """отправить ответ клиенту"""
        if status == 200 and not msg:
            msg = 'OK'
        self.wfile += f'HTTP/1.1 {status} {msg}\r\n'.encode('utf-8')

    def send_error(self, status: int):
        """после этого метода не требуется отправка headers"""

        if status == 400:
            self.send_response(status, msg='Bad Requestr')
            html = self.http_errors.BAD_REQUEST
            self.send_header('Connection', 'close')
        elif status == 401:
            self.send_response(status, msg='Not Authorized')
            html = self.http_errors.UNAUTHORIZED
            self.send_header('WWW-Authenticate', 'Basic realm=""')
        elif status == 403:
            self.send_response(status, msg='Forbidden')
            html = self.http_errors.FORBIDDEN
        elif status == 404:
            self.send_response(status, msg='Not Found')
            html = self.http_errors.NOT_FOUND
        elif status == 500:
            self.send_response(status, msg='Internal Server Error')
            html = self.http_errors.INTERNAL_ERROR
        else:
            self.send_response(status)
            html = ''

        html = html.encode('utf-8')
        length = str(len(html))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', length)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Date', self.date)
        self.send_header('Server', self.server_name)
        self.end_headers()
        self.send_data(html)

    async def do_GET(self):

        if self.path == '/':
            await self.send_file('index.html')
        else:
            await self.send_file()


class AsyncHTTPServer:
    """Простой ассинхронный Http сервер"""
    def __init__(self, stream_server, handler_class):
        
        self.stream_server = stream_server
        self.IP_ADDR = self.stream_server.IP
        # self.PORT = self.stream_server.properties.get['HttpPort']
        self.PORT = 80

        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.check_hostname = False
        # self.ssl_context.load_cert_chain(certfile='cert.pem', keyfile='privkey.pem')

        self.MAX_HEADER_LENGHT = 8192
        self.HEAD_TERMINATOR = b'\r\n\r\n'
        self.ASYNC_SOCK_TIMEOUT = 30

        self.handler_class = handler_class
        self.loop = asyncio.get_event_loop()

    async def handle_connection(self, reader, writer):
        time_point = time.time()
        buffer = b''
        try:
            while True:
                data = await asyncio.wait_for(reader.read(1024), 30)
                buffer += data
                if self.HEAD_TERMINATOR in buffer:
                    _head = buffer.split(self.HEAD_TERMINATOR)[0]
                    _handle = self.handler_class(_head, reader, writer, stream_server=self.stream_server)
                    await _handle.handle_request()
                    del _handle
                    break
                elif len(buffer) > self.MAX_HEADER_LENGHT:
                    _handle = self.handler_class('', reader, writer, True, stream_server=self.stream_server)
                    await _handle.handle_request()
                    del _handle
                    break
                elif not data:
                    break
                elif time.time() - time_point > 30:
                    raise TimeoutError

        except (asyncio.TimeoutError, TimeoutError):
            # print('соединение разорвано по таймауту')
            pass
        except OSError:
            # print('ошибка на сокете')
            pass
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                print('err closed sock')

    async def _run_server(self):
        server = await asyncio.start_server(
            self.handle_connection,
            self.IP_ADDR,
            self.PORT
        )
        async with server:
            await server.serve_forever()
    
    def run(self) -> None:
        self.loop.create_task(self._run_server())








