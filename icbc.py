# # Install required packages
# pip install flask flask-cors requests PyYAML twilio
# # Run the Flask app
# python icbc-flask-app.py




    
    
# /stop-search (POST)    
# /search-status (GET)    
# /config (post)
#{
#     "icbc": {
#         "drvrLastName": "your_last_name",
#         "licenceNumber": "your_license",
#         "keyword": "your_keyword",
#         "expactAfterDate": "2025-01-13",
#         "expactBeforeDate": "2025-02-05",
#         "expactAfterTime": "09:00",
#         "expactBeforeTime": "17:00",
#         "examClass": 5
#     },
#     "gmail": {
#         "sender_address": "your_email@gmail.com",
#         "sender_pass": "your_app_password",
#         "receiver_address": "recipient@gmail.com"
#     }
# }


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
from twilio.rest import Client
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html

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
BRANCH_NAMES = {
    "274": "Burnaby claim centre (Wayburne Drive)",
    "271": "Newton claim centre (68 Avenue)",
    "8": "North Vancouver driver licensing",
    "93": "Richmond (Lansdowne Centre)",
    "273": "Richmond claim centre (Elmbridge Way)",
    "275": "Vancouver claim centre (Kingsway)",
    "9": "Vancouver (Point Grey)",
    "11": "Surrey driver licensing",
    "269": "Surrey claim centre (152A St.)"
}
user_config = {
    'icbc': {
        'branchId': None 
    },
    'gmail': {},
    'phone': None
}
search_history = {
    'start_time': None,
    'found_appointments': []
}


TWILIO_ACCOUNT_SID = ''
TWILIO_AUTH_TOKEN = ''
TWILIO_PHONE_NUMBER = ''


# def sendEmail(mail_content, branch_name):
#     """Send email using Gmail"""
#     if not all(key in user_config['gmail'] for key in ['sender_address', 'sender_pass', 'receiver_address']):
#         print("Email configuration missing")
#         return False
        
#     message = MIMEMultipart()
#     message['From'] = user_config['gmail']['sender_address']
#     message['To'] = user_config['gmail']['receiver_address']
#     message['Subject'] = f'ICBC Bot Notification - Appointment Found at {branch_name}!'
#     message.attach(MIMEText(mail_content, 'plain'))
    
#     try:
#         session = smtplib.SMTP('smtp.gmail.com', 587)
#         session.starttls()
#         session.login(user_config['gmail']['sender_address'], user_config['gmail']['sender_pass'])
#         text = message.as_string()
#         session.sendmail(user_config['gmail']['sender_address'], user_config['gmail']['receiver_address'], text)
#         session.quit()
#         print('Mail Sent\n' + mail_content)
#         return True
#     except Exception as e:
#         print(f"Error sending email: {str(e)}")
#         return False

def sendEmail(mail_content, branch_name):
    """Send HTML email using Gmail"""
    if not all(key in user_config['gmail'] for key in ['sender_address', 'sender_pass', 'receiver_address']):
        print("Email configuration missing")
        return False
        
    message = MIMEMultipart('alternative')
    message['From'] = user_config['gmail']['sender_address']
    message['To'] = user_config['gmail']['receiver_address']
    message['Subject'] = f'ICBC Bot Notification - Appointment Found at {branch_name}!'
    
    # Create plain text version
    text_content = mail_content + "\n\nBook your appointment here: https://onlinebusiness.icbc.com/webdeas-ui/login"
    
    # Create HTML version
    html_content = f"""
    <html>
        <head></head>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #004085;">ICBC Appointment Notification</h2>
                <div style="white-space: pre-line;">
                    {html.escape(mail_content)}
                </div>
                <div style="margin-top: 30px; text-align: center;">
                    <a href="https://onlinebusiness.icbc.com/webdeas-ui/login" 
                       style="background-color: #007bff; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 4px; display: inline-block;">
                        Book Your Appointment Now
                    </a>
                </div>
            </div>
        </body>
    </html>
    """
    
    # Attach both versions
    message.attach(MIMEText(text_content, 'plain'))
    message.attach(MIMEText(html_content, 'html'))
    
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

def sendSMS(content, branch_name):
    """Send SMS using Twilio"""
    if not user_config.get('phone'):
        print("Phone number not configured")
        return False
        
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Create a shorter message for SMS
        sms_content = f"ICBC Appointment Found at {branch_name}!\n\n"
        sms_content += "Available slots found. Check your email for details.\n"
        sms_content += "Book here: https://onlinebusiness.icbc.com/webdeas-ui/login"
        
        message = client.messages.create(
            body=sms_content,
            from_=TWILIO_PHONE_NUMBER,
            to=user_config['phone']
        )
        print(f'SMS sent: {message.sid}')
        return True
    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
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
    if not all(key in user_config['icbc'] for key in ['drvrLastName', 'licenceNumber', 'examClass', 'branchId']):
        print("ICBC appointment configuration missing")
        return []
        
    appointment_url = "https://onlinebusiness.icbc.com/deas-api/v1/web/getAvailableAppointments"
    headers = {
        'Content-type': 'application/json',
        'Authorization': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    appointment_request = {
        "aPosID": int(user_config['icbc']['branchId']),  # Convert to integer
        "examType": f"{user_config['icbc']['examClass']}-R-1",
        "examDate": user_config['icbc']['expactAfterDate'],
        "ignoreReserveTime": "false",
        "prfDaysOfWeek": "[0,1,2,3,4,5,6]",
        "prfPartsOfDay": "[0,1]",
        "lastName": user_config['icbc']['drvrLastName'],
        "licenseNumber": user_config['icbc']['licenceNumber']
    }
    
    try:
        response = requests.post(appointment_url, data=json.dumps(appointment_request), headers=headers)
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

def get_branch_name(branch_id):
    """Get branch name from branch ID"""
    return BRANCH_NAMES.get(str(branch_id), f"Unknown Branch ({branch_id})")

# def check_appointments():
#     """Check for available appointments"""
#     token = getToken()
#     if not token:
#         return False
    
#     appointments = getAppointments(token)
#     matching_appointments = []
    
#     branch_id = str(user_config['icbc']['branchId'])
#     branch_name = get_branch_name(branch_id)
    
#     for appointment in appointments:
#         if appointmentMatchRequirement(appointment):
#             matching_appointments.append({
#                 'date': appointment["appointmentDt"]["date"],
#                 'time': appointment["startTm"],
#                 'branch': branch_name  # Use the mapped branch name
#             })

#     if matching_appointments:
#         # Store found appointments in search history
#         search_history['found_appointments'].extend(matching_appointments)
        
#         mail_header = "Good news! We found available appointments that match your criteria:\n"
#         mail_content = ""
#         prevDate = ""
        
#         for apt in matching_appointments:
#             if prevDate != apt['date']:
#                 mail_content += '\n\n' + apt['date'] + ':'
#                 prevDate = apt['date']
#             mail_content += f'\n\t{apt["time"]} at {apt["branch"]}'
            
#         mail_content += "\n\nPlease visit ICBC's website to book your preferred slot."
        
#         sendEmail(mail_header + mail_content, branch_name)
#         return True
#     return False

def check_appointments():
    """Check for available appointments"""
    token = getToken()
    if not token:
        return False
    
    appointments = getAppointments(token)
    matching_appointments = []
    
    branch_id = str(user_config['icbc']['branchId'])
    branch_name = get_branch_name(branch_id)
    
    for appointment in appointments:
        if appointmentMatchRequirement(appointment):
            matching_appointments.append({
                'date': appointment["appointmentDt"]["date"],
                'time': appointment["startTm"],
                'branch': branch_name
            })

    if matching_appointments:
        search_history['found_appointments'].extend(matching_appointments)
        
        mail_header = "Good news! We found available appointments that match your criteria:\n"
        mail_content = ""
        prevDate = ""
        
        for apt in matching_appointments:
            if prevDate != apt['date']:
                mail_content += '\n\n' + apt['date'] + ':'
                prevDate = apt['date']
            mail_content += f'\n\t{apt["time"]} at {apt["branch"]}'
        
        # Send both email and SMS
        email_sent = sendEmail(mail_header + mail_content, branch_name)
        sms_sent = sendSMS(mail_header + mail_content, branch_name)
        
        return email_sent or sms_sent
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
        time.sleep(10)  # Check every 10 seconds

def start_search_thread():
    """Helper function to start the search thread"""
    global search_running, search_thread
    
    # Stop any existing search
    if search_running and search_thread:
        search_running = False
        search_thread.join()
    
    # Start new search
    search_running = True
    search_history['start_time'] = datetime.now()
    search_history['found_appointments'] = []  # Reset found appointments
    search_thread = threading.Thread(target=background_search)
    search_thread.start()

@app.route('/search-history', methods=['GET'])
def get_search_history():
    """Get the search history including start time and found appointments"""
    return jsonify({
        "start_time": search_history['start_time'].strftime("%Y-%m-%d %H:%M:%S") if search_history['start_time'] else None,
        "found_appointments": search_history['found_appointments'],
        "is_searching": search_running
    })

@app.route('/test', methods=['GET'])
def test():
    """Simple test endpoint"""
    return jsonify({
        "status": "success",
        "message": "ICBC Backend is running!",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# @app.route('/config', methods=['POST'])
# def set_config():
#     """Set user configuration and automatically start search"""
#     try:
#         config = request.json
#         if not isinstance(config, dict):
#             return jsonify({"status": "error", "message": "Invalid configuration format"}), 400
            
#         # Validate ICBC config
#         icbc_config = config.get('icbc', {})
#         required_icbc_fields = [
#             'drvrLastName', 'licenceNumber', 'keyword', 'examClass',
#             'expactAfterDate', 'expactBeforeDate', 'expactAfterTime', 'expactBeforeTime',
#             'branchId'  # Add branchId to required fields
#         ]
        
#         if not all(field in icbc_config for field in required_icbc_fields):
#             return jsonify({
#                 "status": "error", 
#                 "message": f"Missing required ICBC fields. Required: {', '.join(required_icbc_fields)}"
#             }), 400
            
#         # Validate Gmail config
#         gmail_config = config.get('gmail', {})
#         required_gmail_fields = ['sender_address', 'sender_pass', 'receiver_address']
        
#         if not all(field in gmail_config for field in required_gmail_fields):
#             return jsonify({
#                 "status": "error", 
#                 "message": f"Missing required Gmail fields. Required: {', '.join(required_gmail_fields)}"
#             }), 400
            
#         # Update configuration
#         user_config['icbc'] = icbc_config
#         user_config['gmail'] = gmail_config
        
#         # Automatically start the search
#         start_search_thread()
        
#         return jsonify({
#             "status": "success",
#             "message": "Configuration updated and search started automatically - you will receive an email when an appointment is found"
#         })
#     except Exception as e:
#         return jsonify({
#             "status": "error",
#             "message": f"Error updating configuration: {str(e)}"
#         }), 400

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
            'expactAfterDate', 'expactBeforeDate', 'expactAfterTime', 'expactBeforeTime',
            'branchId'
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
        user_config['phone'] = config.get('phone')  # Add phone number
        
        # Automatically start the search
        start_search_thread()
        
        return jsonify({
            "status": "success",
            "message": "Configuration updated and search started automatically - you will receive email and SMS notifications when an appointment is found"
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
        "search_status": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running",
        "search_start_time": search_history['start_time'].strftime("%Y-%m-%d %H:%M:%S") if search_history['start_time'] else None
    })

@app.route('/search-status', methods=['GET'])
def search_status():
    """Get the current search status"""
    return jsonify({
        "searching": search_running,
        "search_start_time": search_history['start_time'].strftime("%Y-%m-%d %H:%M:%S") if search_history['start_time'] else None,
        "found_appointments_count": len(search_history['found_appointments']),
        "message": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running"
    })
    
@app.route('/stop-search', methods=['POST'])
def stop_search():
    """Stop the appointment search"""
    global search_running
    if search_running:
        search_running = False
        return jsonify({
            "status": "success", 
            "message": "Search stopped",
            "search_duration": str(datetime.now() - search_history['start_time']) if search_history['start_time'] else None
        })
    return jsonify({"status": "error", "message": "No search running"})



@app.route('/check-sms-config', methods=['GET'])
def check_sms_config():
    """Check SMS configuration and Twilio credentials"""
    try:
        # Check if Twilio credentials are set
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
            return jsonify({
                "status": "error",
                "message": "Twilio credentials are not properly configured",
                "details": {
                    "account_sid_set": bool(TWILIO_ACCOUNT_SID),
                    "auth_token_set": bool(TWILIO_AUTH_TOKEN),
                    "phone_number_set": bool(TWILIO_PHONE_NUMBER)
                }
            }), 400

        # Try to initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Test if we can access the account info
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        
        # Check if there's a phone number configured in the current user session
        phone_configured = bool(user_config.get('phone'))
        
        return jsonify({
            "status": "success",
            "message": "Twilio configuration is valid",
            "details": {
                "account_status": account.status,
                "phone_number": TWILIO_PHONE_NUMBER,
                "user_phone_configured": phone_configured,
                "current_user_phone": user_config.get('phone') if phone_configured else None
            }
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error checking Twilio configuration: {str(e)}",
            "details": {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        }), 500


if __name__ == '__main__':
    print("Starting Flask server on port 8888...")
    app.run(host='0.0.0.0', port=8888)


# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import requests
# import json
# from datetime import datetime
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# import time
# import threading

# # Initialize Flask app
# app = Flask(__name__)
# CORS(app, resources={r"/*": {"origins": "*"}})

# # Add CORS headers to all responses
# @app.after_request
# def after_request(response):
#     response.headers.add('Access-Control-Allow-Origin', '*')
#     response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
#     response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
#     return response

# # Global variables
# search_running = False
# search_thread = None
# user_config = {
#     'icbc': {},
#     'gmail': {}
# }

# # Combined sendEmail function
# def sendEmail(mail_content):
#     """Send email using Gmail"""
#     if not all(key in user_config['gmail'] for key in ['sender_address', 'sender_pass', 'receiver_address']):
#         print("Email configuration missing")
#         return False

#     message = MIMEMultipart()
#     message['From'] = user_config['gmail']['sender_address']
#     message['To'] = user_config['gmail']['receiver_address']
#     message['Subject'] = 'ICBC Bot Notification - Appointment Found!'
#     message.attach(MIMEText(mail_content, 'plain'))

#     try:
#         session = smtplib.SMTP('smtp.gmail.com', 587)
#         session.starttls()
#         session.login(user_config['gmail']['sender_address'], user_config['gmail']['sender_pass'])
#         text = message.as_string()
#         session.sendmail(user_config['gmail']['sender_address'], user_config['gmail']['receiver_address'], text)
#         session.quit()
#         print('Mail Sent\n' + mail_content)
#         return True
#     except Exception as e:
#         print(f"Error sending email: {str(e)}")
#         return False

# def getToken():
#     """Get authorization token from ICBC"""
#     if not all(key in user_config['icbc'] for key in ['drvrLastName', 'licenceNumber', 'keyword']):
#         print("ICBC login configuration missing")
#         return ""

#     login_url = "https://onlinebusiness.icbc.com/deas-api/v1/webLogin/webLogin"
#     headers = {
#         'Content-type': 'application/json',
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
#     }
#     payload = {
#         "drvrLastName": user_config['icbc']['drvrLastName'],
#         "licenceNumber": user_config['icbc']['licenceNumber'],
#         "keyword": user_config['icbc']['keyword']
#     }
#     try:
#         response = requests.put(login_url, data=json.dumps(payload), headers=headers)
#         if response.status_code == 200:
#             return response.headers["Authorization"]
#         return ""
#     except Exception as e:
#         print(f"Error during login: {str(e)}")
#         return ""

# def getAppointments(token):
#     """Get available appointments from ICBC"""
#     if not all(key in user_config['icbc'] for key in ['drvrLastName', 'licenceNumber', 'examClass']):
#         print("ICBC appointment configuration missing")
#         return []

#     appointment_url = "https://onlinebusiness.icbc.com/deas-api/v1/web/getAvailableAppointments"
#     headers = {
#         'Content-type': 'application/json',
#         'Authorization': token,
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
#     }
#     point_grey = {
#         "aPosID": 9,
#         "examType": f"{user_config['icbc']['examClass']}-R-1",
#         "examDate": user_config['icbc']['expactAfterDate'],
#         "ignoreReserveTime": "false",
#         "prfDaysOfWeek": "[0,1,2,3,4,5,6]",
#         "prfPartsOfDay": "[0,1]",
#         "lastName": user_config['icbc']['drvrLastName'],
#         "licenseNumber": user_config['icbc']['licenceNumber']
#     }
#     try:
#         response = requests.post(appointment_url, data=json.dumps(point_grey), headers=headers)
#         if response.status_code == 200:
#             return response.json()
#         return []
#     except Exception as e:
#         print(f"Error getting appointments: {str(e)}")
#         return []

# def appointmentMatchRequirement(appointment):
#     """Check if appointment matches requirements"""
#     if not all(key in user_config['icbc'] for key in ['expactBeforeDate', 'expactAfterDate', 'expactAfterTime', 'expactBeforeTime']):
#         print("Date/time configuration missing")
#         return False

#     try:
#         appointmentDate = appointment["appointmentDt"]["date"]
#         thatDate = datetime.strptime(appointmentDate, "%Y-%m-%d")
#         beforeDate = datetime.strptime(user_config['icbc']['expactBeforeDate'], "%Y-%m-%d")
#         afterDate = datetime.strptime(user_config['icbc']['expactAfterDate'], "%Y-%m-%d")

#         appointmentTime = appointment["startTm"]
#         thatTime = datetime.strptime(appointmentTime, "%H:%M")
#         afterTime = datetime.strptime(user_config['icbc']['expactAfterTime'], "%H:%M")
#         beforeTime = datetime.strptime(user_config['icbc']['expactBeforeTime'], "%H:%M")

#         return afterDate <= thatDate <= beforeDate and afterTime <= thatTime <= beforeTime
#     except Exception as e:
#         print(f"Error checking appointment: {str(e)}")
#         return False

# def check_appointments():
#     """Check for available appointments"""
#     token = getToken()
#     if not token:
#         return False

#     appointments = getAppointments(token)
#     matching_appointments = []

#     for appointment in appointments:
#         if appointmentMatchRequirement(appointment):
#             matching_appointments.append({
#                 'date': appointment["appointmentDt"]["date"],
#                 'time': appointment["startTm"]
#             })

#     if matching_appointments:
#         mail_header = "Good news! We found available appointments that match your criteria:\n"
#         mail_content = ""
#         prevDate = ""

#         for apt in matching_appointments:
#             if prevDate != apt['date']:
#                 mail_content += '\n\n' + apt['date'] + ':'
#                 prevDate = apt['date']
#             mail_content += '\n\t' + apt['time']

#         mail_content += "\n\nPlease visit ICBC's website to book your preferred slot."

#         sendEmail(mail_header + mail_content)
#         return True
#     return False

# def background_search():
#     """Background thread for continuous searching"""
#     global search_running
#     while search_running:
#         print("Checking for appointments...")
#         if check_appointments():
#             search_running = False
#             print("Appointment found! Search stopped.")
#             break
#         time.sleep(300)  # Check every 5 minutes

# def start_search_thread():
#     """Helper function to start the search thread"""
#     global search_running, search_thread

#     # Stop any existing search
#     if search_running and search_thread:
#         search_running = False
#         search_thread.join()

#     # Start new search
#     search_running = True
#     search_thread = threading.Thread(target=background_search)
#     search_thread.start()

# @app.route('/test', methods=['GET'])
# def test():
#     """Simple test endpoint"""
#     return jsonify({
#         "status": "success",
#         "message": "ICBC Backend is running!",
#         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     })

# @app.route('/config', methods=['POST'])
# def set_config():
#     """Set user configuration and automatically start search"""
#     try:
#         config = request.json
#         if not isinstance(config, dict):
#             return jsonify({"status": "error", "message": "Invalid configuration format"}), 400

#         # Validate ICBC config
#         icbc_config = config.get('icbc', {})
#         required_icbc_fields = [
#             'drvrLastName', 'licenceNumber', 'keyword', 'examClass',
#             'expactAfterDate', 'expactBeforeDate', 'expactAfterTime', 'expactBeforeTime'
#         ]

#         if not all(field in icbc_config for field in required_icbc_fields):
#             return jsonify({
#                 "status": "error",
#                 "message": f"Missing required ICBC fields. Required: {', '.join(required_icbc_fields)}"
#             }), 400

#         # Validate Gmail config
#         gmail_config = config.get('gmail', {})
#         required_gmail_fields = ['sender_address', 'sender_pass', 'receiver_address']

#         if not all(field in gmail_config for field in required_gmail_fields):
#             return jsonify({
#                 "status": "error",
#                 "message": f"Missing required Gmail fields. Required: {', '.join(required_gmail_fields)}"
#             }), 400

#         # Update configuration
#         user_config['icbc'] = icbc_config
#         user_config['gmail'] = gmail_config

#         # Automatically start the search
#         start_search_thread()

#         return jsonify({
#             "status": "success",
#             "message": "Configuration updated and search started automatically - you will receive an email when an appointment is found"
#         })
#     except Exception as e:
#         return jsonify({
#             "status": "error",
#             "message": f"Error updating configuration: {str(e)}"
#         }), 400

# @app.route('/get-config', methods=['GET'])
# def get_config():
#     """Get current configuration"""
#     return jsonify({
#         "config": user_config,
#         "search_status": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running"
#     })

# @app.route('/search-status', methods=['GET'])
# def search_status():
#     """Get the current search status"""
#     return jsonify({
#         "searching": search_running,
#         "message": "Search is running - you will receive an email when an appointment is found" if search_running else "Search is not running"
#     })


# @app.route('/get-appointments', methods=['GET'])
# def get_appointments():
#     """Retrieve the last matching appointments"""
#     token = getToken()
#     if not token:
#         return jsonify([])

#     appointments = getAppointments(token)
#     matching_appointments = []

#     for appointment in appointments:
#         if appointmentMatchRequirement(appointment):
#             matching_appointments.append({
#                 'date': appointment["appointmentDt"]["date"],
#                 'time': appointment["startTm"]
#             })

#     return jsonify(matching_appointments)


# @app.route('/stop-search', methods=['POST'])
# def stop_search():
#     """Stop the appointment search"""
#     global search_running
#     if search_running:
#         search_running = False
#         return jsonify({"status": "success", "message": "Search stopped"})
#     return jsonify({"status": "error", "message": "No search running"})

# if __name__ == '__main__':
#     print("Starting Flask server on port 8888...")
#     app.run(host='0.0.0.0', port=8888)
