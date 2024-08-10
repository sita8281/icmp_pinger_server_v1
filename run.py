import asyncio
import sys

from simple_logger import Logger
from stream_server import Server
from pinger import Pinger
from micro_async_http.http_request_handler import HTTPRequestHandler
from micro_async_http.http_server import AsyncHTTPServer
from stream_server_proto.protocol import Protocol
from stream_server_proto.stream_request_handler import RequestHandler


def main():
    event_loop = asyncio.get_event_loop()
    logger = Logger(file_path="logs.txt")
    server = Server(logger=logger, proto=Protocol(), handler=RequestHandler(), pinger=Pinger())
    web_server = AsyncHTTPServer(server, handler_class=HTTPRequestHandler)

    web_server.run()
    server.run()

    try:
        event_loop.run_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == '__main__':
    main()

    