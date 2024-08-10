import asyncio
import time
import mimetypes
import os
import datetime
import ssl








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








