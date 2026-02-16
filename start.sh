#!/bin/bash
cd /root/o11yplayground.com/backend
source venv/bin/activate
nohup uvicorn main:app --host 127.0.0.1 --port 8094 > /root/o11yplayground.com/backend.log 2>&1 &
echo $! > /root/o11yplayground.com/backend.pid
echo "Started backend on port 8094 (PID: $(cat /root/o11yplayground.com/backend.pid))"
