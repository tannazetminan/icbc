from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import time
import threading

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Global variables
search_running = False
search_thread = None
user_config = {
    'icbc': {},
    'gmail': {}
}

# Combined sendEmail function
def sendEmail(mail_content):
    """Send email using Gmail"""
    if not all(key in user_config['gmail'] for key in ['sender_address', 'sender_pass', 'receiver_address']):
        print("Email configuration missing")
        return False

    message = MIMEMultipart()
    message['From'] = user_config['gmail']['sender_address']
    message['To'] = user_config['gmail']['receiver_address']
    message['Subject'] = 'ICBC Bot Notification - Appointment Found!'
    message.attach(MIMEText(mail_content, 'plain'))

    try:
        session = smtplib.SMTP('smtp.gmail.com', 587)
        session.starttls()
        session.login(user_config['gmail']['sender_address'], user_config['gmail']['sender_pass'])
        text = message.as_string()
        session.sendmail(user_config['gmail']['sender_address'], user_config['gmail']['receiver_address'], text)
        session.quit()
        print('Mail Sent\n' + mail_content)
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

def getToken():
    """Get authorization token from ICBC"""
    if not all(key in user_config['icbc'] for key in ['drvrLastName', 'licenceNumber', 'keyword']):
        print("ICBC login configuration missing")
        return ""

    login_url = "https://onlinebusiness.icbc.com/deas-api/v1/webLogin/webLogin"
    headers = {
        'Content-type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    payload = {
        "drvrLastName": user_config['icbc']['drvrLastName'],
        "licenceNumber": user_config['icbc']['licenceNumber'],
        "keyword": user_config['icbc']['keyword']
    }
    try:
        response = requests.put(login_url, data=json.dumps(payload), headers=headers)
        if response.status_code == 200:
            return response.headers["Authorization"]
        return ""
    except Exception as e:
        print(f"Error during login: {str(e)}")
        return ""

def getAppointments(token):
    """Get available appointments from ICBC"""
    if not all(key in user_config['icbc'] for key in ['drvrLastName', 'licenceNumber', 'examClass']):
        print("ICBC appointment configuration missing")
        return []

    appointment_url = "https://onlinebusiness.icbc.com/deas-api/v1/web/getAvailableAppointments"
    headers = {
        'Content-type': 'application/json',
        'Authorization': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    point_grey = {
        "aPosID": 9,
        "examType": f"{user_config['icbc']['examClass']}-R-1",
        "examDate": user_config['icbc']['expactAfterDate'],
        "ignoreReserveTime": "false",
        "prfDaysOfWeek": "[0,1,2,3,4,5,6]",
        "prfPartsOfDay": "[0,1]",
        "lastName": user_config['icbc']['drvrLastName'],
        "licenseNumber": user_config['icbc']['licenceNumber']
    }
    try:
        response = requests.post(appointment_url, data=json.dumps(point_grey), headers=headers)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"Error getting appointments: {str(e)}")
        return []

def appointmentMatchRequirement(appointment):
    """Check if appointment matches requirements"""
    if not all(key in user_config['icbc'] for key in ['expactBeforeDate', 'expactAfterDate', 'expactAfterTime', 'expactBeforeTime']):
        print("Date/time configuration missing")
        return False

    try:
        appointmentDate = appointment["appointmentDt"]["date"]
        thatDate = datetime.strptime(appointmentDate, "%Y-%m-%d")
        beforeDate = datetime.strptime(user_config['icbc']['expactBeforeDate'], "%Y-%m-%d")
        afterDate = datetime.strptime(user_config['icbc']['expactAfterDate'], "%Y-%m-%d")

        appointmentTime = appointment["startTm"]
        thatTime = datetime.strptime(appointmentTime, "%H:%M")
        afterTime = datetime.strptime(user_config['icbc']['expactAfterTime'], "%H:%M")
        beforeTime = datetime.strptime(user_config['icbc']['expactBeforeTime'], "%H:%M")

        return afterDate <= thatDate <= beforeDate and afterTime <= thatTime <= beforeTime
    except Exception as e:
        print(f"Error checking appointment: {str(e)}")
        return False

def check_appointments():
    """Check for available appointments"""
    token = getToken()
    if not token:
        return False

    appointments = getAppointments(token)
    matching_appointments = []

    for appointment in appointments:
        if appointmentMatchRequirement(appointment):
            matching_appointments.append({
                'date': appointment["appointmentDt"]["date"],
                'time': appointment["startTm"]
            })

    if matching_appointments:
        mail_header = "Good news! We found available appointments that match your criteria:\n"
        mail_content = ""
        prevDate = ""

        for apt in matching_appointments:
            if prevDate != apt['date']:
                mail_content += '\n\n' + apt['date'] + ':'
                prevDate = apt['date']
            mail_content += '\n\t' + apt['time']

        mail_content += "\n\nPlease visit ICBC's website to book your preferred slot."

        sendEmail(mail_header + mail_content)
        return True
    return False

def background_search():
    """Background thread for continuous searching"""
    global search_running
    while search_running:
        print("Checking for appointments...")
        if check_appointments():
            search_running = False
            print("Appointment found! Search stopped.")
            break
        time.sleep(300)  # Check every 5 minutes

def start_search_thread():
    """Helper function to start the search thread"""
    global search_running, search_thread

    # Stop any existing search
    if search_running and search_thread:
        search_running = False
        search_thread.join()

    # Start new search
    search_running = True
    search_thread = threading.Thread(target=background_search)
    search_thread.start()

@app.route('/test', methods=['GET'])
def test():
    """Simple test endpoint"""
    return jsonify({
        "status": "success",
        "message": "ICBC Backend is running!",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/config', methods=['POST'])
def set_config():
    """Set user configuration and automatically start search"""
    try:
        config = request.json
        if not isinstance(config, dict):
            return jsonify({"status": "error", "message": "Invalid configuration format"}), 400

        # Validate ICBC config
        icbc_config = config.get('icbc', {})
        required_icbc_fields = [
            'drvrLastName', 'licenceNumber', 'keyword', 'examClass',
            'expactAfterDate', 'expactBeforeDate', 'expactAfterTime', 'expactBeforeTime'
        ]

        if not all(field in icbc_config for field in required_icbc_fields):
            return jsonify({
                "status": "error",
                "message": f"Missing required ICBC fields. Required: {', '.join(required_icbc_fields)}"
            }), 400

        # Validate Gmail config
        gmail_config = config.get('gmail', {})
        required_gmail_fields = ['sender_address', 'sender_pass', 'receiver_address']

        if not all(field in gmail_config for field in required_gmail_fields):
            return jsonify({
                "status": "error",
                "message": f"Missing required Gmail fields. Required: {', '.join(required_gmail_fields)}"
            }), 400

        # Update configuration
        user_config['icbc'] = icbc_config
        user_config['gmail'] = gmail_config

        # Automatically start the search
        start_search_thread()

        return jsonify({
            "status": "success",
            "message": "Configuration updated and search started automatically - you will receive an email when an appointment is found"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error updating configuration: {str(e)}"
        }), 400

@app.route('/get-config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        "config": user_config,
        "search_status": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running"
    })

@app.route('/search-status', methods=['GET'])
def search_status():
    """Get the current search status"""
    return jsonify({
        "searching": search_running,
        "message": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running"
    })


@app.route('/get-appointments', methods=['GET'])
def get_appointments():
    """Retrieve the last matching appointments"""
    token = getToken()
    if not token:
        return jsonify([])

    appointments = getAppointments(token)
    matching_appointments = []

    for appointment in appointments:
        if appointmentMatchRequirement(appointment):
            matching_appointments.append({
                'date': appointment["appointmentDt"]["date"],
                'time': appointment["startTm"]
            })

    return jsonify(matching_appointments)


@app.route('/stop-search', methods=['POST'])
def stop_search():
    """Stop the appointment search"""
    global search_running
    if search_running:
        search_running = False
        return jsonify({"status": "success", "message": "Search stopped"})
    return jsonify({"status": "error", "message": "No search running"})

if __name__ == '__main__':
    print("Starting Flask server on port 8888...")
    app.run(host='0.0.0.0', port=8888)
