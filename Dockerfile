FROM python:3.9

COPY . /pinger_server
WORKDIR /pinger_server
RUN pip install -r requirements.txt
EXPOSE 2323
EXPOSE 8080
CMD ["python", "run.py"]