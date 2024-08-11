import struct
import zlib
import asyncio


class Protocol:
    """Протокол передачи данных поверх TCP
    Суть проста, сегмент состоит из двух полей: HEADER и DATA
    - header служит для обозначения длинны сегмента в байтах, передаётся в виде STRUCT int
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