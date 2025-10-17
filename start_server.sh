#!/bin/bash
# Science3 Flask Server Manager

cd "$(dirname "$0")"

case "$1" in
    start)
        echo "Starting Flask server..."
        # 既存のプロセスを確認
        if pgrep -f "python.*app.py" > /dev/null; then
            echo "Server is already running!"
            exit 1
        fi
        # バックグラウンドで起動
        nohup python app.py > app.log 2>&1 &
        echo "Server started! PID: $!"
        echo "Access: http://127.0.0.1:5014"
        echo "Logs: tail -f app.log"
        ;;
    
    stop)
        echo "Stopping Flask server..."
        pkill -f "python.*app.py"
        echo "Server stopped!"
        ;;
    
    restart)
        echo "Restarting Flask server..."
        $0 stop
        sleep 2
        $0 start
        ;;
    
    status)
        if pgrep -f "python.*app.py" > /dev/null; then
            echo "✅ Server is running"
            echo "PID: $(pgrep -f 'python.*app.py')"
            echo "Access: http://127.0.0.1:5014"
        else
            echo "❌ Server is not running"
        fi
        ;;
    
    logs)
        echo "=== Flask Server Logs (Press Ctrl+C to exit) ==="
        tail -f app.log
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the Flask server"
        echo "  stop    - Stop the Flask server"
        echo "  restart - Restart the Flask server"
        echo "  status  - Check server status"
        echo "  logs    - View server logs"
        exit 1
        ;;
esac
