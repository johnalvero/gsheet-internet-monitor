FROM python:3-slim

RUN mkdir /internet-monitor
WORKDIR /internet-monitor

RUN apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY internet-monitor.py .
COPY service_account.json .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python","internet_monitor-v3.py"]
