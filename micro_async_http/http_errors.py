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