#!/bin/bash
if [ -f /root/o11yplayground.com/backend.pid ]; then
    kill $(cat /root/o11yplayground.com/backend.pid) 2>/dev/null
    rm /root/o11yplayground.com/backend.pid
    echo "Stopped backend"
else
    echo "No PID file found"
fi
