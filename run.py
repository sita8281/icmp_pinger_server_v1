import asyncio
import sys

from simple_logger import Logger
from server import Server
from http_request_handler import HTTPRequestHandler
from http_server import AsyncHTTPServer


if __name__ == '__main__':
    event_loop = asyncio.get_event_loop()
    log = Logger(file_path="logs.txt")
    server = Server(logger=log)
    log.set_callback_broadcast(server.broadcast_send)
    web_server = AsyncHTTPServer(server, HTTPRequestHandler)

    event_loop.create_task(web_server.run_server())
    server.run()

    try:
        loop = event_loop.run_forever()
    except KeyboardInterrupt:
        sys.exit(0)