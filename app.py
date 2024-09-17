from flask import Flask, request, render_template, redirect, url_for, jsonify
import smtplib
from email.mime.text import MIMEText
from transformers import pipeline
import os
import sqlite3
from datetime import datetime, timedelta
from dateutil import parser
import re
from flask import jsonify

app = Flask(__name__)

# Initialize AI summarization model (Hugging Face)
summarizer = pipeline('summarization')
ner = pipeline('ner')

# Database setup
DATABASE = 'compliance.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS notices
                      (id INTEGER PRIMARY KEY, notice TEXT, summary TEXT, actions TEXT, response TEXT)''')

    # Check and add new columns if they don't exist
    try:
        cursor.execute("ALTER TABLE notices ADD COLUMN status TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE notices ADD COLUMN deadline TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE notices ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    conn.commit()
    conn.close()

# Summarize Notice
def summarize_notice(text):
    summary = summarizer(text, max_length=10000, min_length=30, do_sample=False)
    return summary[0]['summary_text']

# Update deadline status for missed deadlines
def update_deadline_status():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    today = datetime.now()

    # Update status to 'Deadline Missed' if the deadline is passed and status is not 'Completed'
    cursor.execute("""
        UPDATE notices
        SET status = 'Deadline Missed'
        WHERE status != 'Completed' AND status != 'Deadline Missed' AND DATE(deadline) < DATE(?)
    """, (today,))
    
    conn.commit()
    conn.close()


# Detect Actions with enhanced date parsing and debugging
def detect_actions(text):
    deadline = None
    today = datetime.now()
    error_message = None

    # Normalize the text by removing unnecessary punctuations (e.g., Sept. -> Sept)
    cleaned_text = re.sub(r'[.,]', '', text)

    # Look for lines that start with 'Deadline' and extract the date
    deadline_match = re.search(r'\bDeadline\s*:\s*(.*)', cleaned_text)
    
    if deadline_match:
        deadline_str = deadline_match.group(1).strip()
        print(f"Extracted deadline string: {deadline_str}")
        
        try:
            # Parse the extracted deadline date
            potential_date = parser.parse(deadline_str, fuzzy=True, default=today)
            print(f"Parsed potential date: {potential_date}")

            # Ensure that the parsed date is in the future
            if potential_date > today:
                deadline = potential_date
            else:
                print(f"Parsed date {potential_date} is in the past, ignoring.")

        except (ValueError, TypeError) as e:
            error_message = f"Invalid date detected: {str(e)}"
            print(error_message)

    # Return appropriate actions based on deadline validity
    if deadline:
        if deadline - today <= timedelta(days=15):
            return "Immediate Action Required", deadline.strftime("%Y-%m-%d")
        else:
            return "No immediate action required", deadline.strftime("%Y-%m-%d")
    else:
        if error_message:
            print(error_message)  # Log error for debugging
        return "No valid deadline detected", None




# Function to extract action items from a notice using AI and keyword-based extraction
def extract_actions(notice_text):
    actions = []

    # Define action-related keywords and phrases
    action_keywords = [
        "Action Required", "Review", "Update", "Complete", "Submit", "Conduct", 
        "Ensure", "Provide", "Schedule", "Make necessary amendments", "Document", "Present", "Include","Urgent"
    ]

    # Split the notice text into lines for easier keyword matching
    lines = notice_text.split("\n")

    # Extract lines that contain action-related keywords
    for line in lines:
        for keyword in action_keywords:
            if re.search(rf"\b{keyword}\b", line, re.IGNORECASE):
                actions.append(line.strip())  # Extract the action point and remove extra spaces
                break  # Once a keyword is found, no need to check other keywords for the same line

    # Remove duplicate actions
    actions = list(set(actions))  # Use a set to remove duplicates, then convert back to list

    # Limit the number of actions to 2-3 major bullet points
    actions = actions[:3]

    # Return action points as bullet points
    if actions:
        return "\n".join(f"- {action}" for action in actions)
    else:
        return "No actionable items detected."


# Modify store_notice to include action extraction from AI
def store_notice(notice, summary, actions, response, deadline, status="Pending"):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Ensure the current timestamp is stored in the created_at field
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("INSERT INTO notices (notice, summary, actions, response, deadline, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (notice, summary, actions, response, deadline, status, created_at))
    conn.commit()
    conn.close()


# Example: handling date error in sample email
def send_sample_email():
    # Define sample email content
    subject = "Regulatory Compliance Notice - Comprehensive Audit and Reporting Requirements (Effective Immediately)"
    notice_text = """
Date: September 15, 2024
To: [Chief Compliance Officer], [HSBC]
From: Financial Conduct Authority (FCA)
Reference: FCA-2024/Compliance-Notice-0013

Executive Summary:
The FCA has identified certain areas within the financial services sector that require enhanced monitoring, audit controls, and risk management. This notice mandates immediate action in ensuring that your institution is fully compliant with the regulatory requirements outlined in the following sections. Failure to comply may result in penalties, including monetary fines and legal action.

1. Reporting Requirements:
Your institution is required to submit detailed reports covering the following:

1.1 Anti-Money Laundering (AML) Compliance:

Submit updated AML policies, including any changes in risk assessment criteria.
Provide documentation of training conducted for staff on AML policies.
Ensure submission of all SARs (Suspicious Activity Reports) filed over the last 12 months, along with an action summary for each case.
1.2 Transaction Monitoring:

All large transactions over £10,000 made in the last 6 months must be documented, including customer identification details.
Submit quarterly transaction monitoring reports that assess trends, anomalies, and flagged risks within the institution’s financial operations.
1.3 Capital Adequacy & Liquidity:

Provide detailed reports on capital adequacy ratios as per Basel III standards for the last 4 quarters.
Demonstrate adherence to liquidity requirements, including real-time liquidity data for stress tests conducted in Q3 2024.
1.4 Cybersecurity and Data Protection:

Submit the results of all cybersecurity risk assessments conducted since January 2024.
Provide information on the encryption methods and data storage practices, especially regarding sensitive customer data.
2. Governance and Risk Management Framework:
2.1 Board Oversight and Governance:

Submit minutes of board meetings over the last 12 months that pertain to risk management decisions.
Provide an organizational chart highlighting roles responsible for regulatory compliance, risk management, and audit functions.
2.2 Internal Audit Reports:

Include internal audit reports for Q1-Q3 2024, particularly those related to compliance with FCA’s updated guidelines issued in March 2024.
Highlight corrective actions taken in response to audit findings, if any.
2.3 Risk Management Policies:

Present updated risk management policies that address operational risks, market risks, and liquidity risks, particularly in light of volatile market conditions.
Submit evidence of stress testing conducted, including assumptions, results, and management's interpretation of those tests.
3. Customer Protection and Market Conduct:
3.1 Consumer Complaints Handling:

Provide statistics on customer complaints filed in the last 6 months, categorized by type of complaint (e.g., fraud, service issues).
Outline procedures in place to ensure timely resolution of consumer complaints and any improvements made based on feedback.
3.2 Product Suitability and Fair Dealing:

Demonstrate adherence to product suitability guidelines, ensuring that products sold to customers align with their financial needs and risk profiles.
Submit a list of all high-risk financial products offered, including information on customer risk disclosures provided for each.
3.3 Marketing and Promotional Material Compliance:

Provide copies of all marketing material used for financial products since January 2024, along with the compliance reviews conducted to ensure that these materials are in line with FCA standards.
4. Mandatory Actions and Deadlines:
Action Items:

Submit all requested documentation, reports, and materials by September 30, 2024.
Deadline : September 30, 2024
If your institution requires an extension, you must submit a written request explaining the rationale by September 30, 2024.
Designate a senior officer responsible for coordinating the submission of these materials, who will serve as the primary contact for follow-up inquiries.
Failure to Comply:

Non-compliance with this regulatory notice may lead to enforcement actions including, but not limited to, financial penalties, restricted access to certain financial markets, and reputational damage.
5. Contact Information:
For any questions related to this notice, or if further clarification is required, please contact:

John Doe
Senior Regulatory Officer
Financial Conduct Authority
Phone: +44 20 7066 1000
Email: johndoe@fca.org.uk

This regulatory notice is intended to ensure transparency, accountability, and the protection of both financial markets and consumers. Your cooperation is highly appreciated.

Disclaimer: This communication contains confidential information and is intended for the named addressee(s) only. Any dissemination or unauthorized use of this notice is strictly prohibited.
    """
    
    # Summarize the notice
    summary = summarize_notice(notice_text)
    
    # Extract actions using AI (keyword-based)
    actions = extract_actions(notice_text)

    # Detect deadline using the new detect_deadline function
    deadline = detect_deadline(notice_text)

    # In the upload_notice function, where response_template is generated
    response_template = f"Dear Regulator, \n\nWe acknowledge receipt of your notice regarding:\n\nSummary: {summary}\n\nActions:\n{actions}\n\nThe deadline for compliance is: {deadline if deadline else 'None'}"

    # Store the notice in the database with error handling for malformed dates
    store_notice(notice_text, summary, actions, response_template, deadline, status="Email")

    # Prepare email content
    email_body = f"{notice_text}\n\n"

    # Send email to primary recipient and stakeholders
    primary_recipient = 'recipient@example.com'  # Replace with the actual primary recipient
    stakeholders = ['stakeholder1@example.com', 'stakeholder2@example.com']  # Add actual stakeholder emails

    # SMTP configuration to send email via Mailtrap
    with smtplib.SMTP('smtp.mailtrap.io', 587) as server:
        server.starttls()  # Secure the connection
        server.login('251c59f358b030', 'f31c531232aa31')  # Replace with Mailtrap credentials

        # Send email to primary recipient
        msg = MIMEText(email_body)
        msg['Subject'] = subject
        msg['From'] = 'compliance@example.com'
        msg['To'] = primary_recipient
        server.sendmail('compliance@example.com', primary_recipient, msg.as_string())

        # Send email to stakeholders
        for stakeholder in stakeholders:
            stakeholder_msg = MIMEText(response_template)
            stakeholder_msg['Subject'] = subject
            stakeholder_msg['From'] = 'compliance@example.com'
            stakeholder_msg['To'] = stakeholder
            server.sendmail('compliance@example.com', stakeholder, stakeholder_msg.as_string())
    
    print("Sample email sent and stored.")



    
# Email Distribution (integrated into app)
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = 'compliance@example.com'
    msg['To'] = to_email

    # Simulate sending email via SMTP
    with smtplib.SMTP('smtp.mailtrap.io', 587, timeout=30) as server:
        server.ehlo()  # Greet the server
        server.starttls()  # Secure the connection
        server.ehlo()  # Re-identify as secure
        server.login('251c59f358b030', 'f31c531232aa31')  # Replace with actual credentials
        server.sendmail('compliance@example.com', to_email, msg.as_string())


def detect_deadline(notice_text):
    # Search for "Deadline" or similar keywords in the notice text
    deadline_match = re.search(r'Deadline\s*:\s*(.*)', notice_text, re.IGNORECASE)

    # If a match is found, try to parse the date
    if deadline_match:
        deadline_str = deadline_match.group(1).strip()
        
        try:
            # Parse the extracted deadline date
            deadline = parser.parse(deadline_str, fuzzy=True).strftime("%Y-%m-%d")
            return deadline
        except (ValueError, TypeError):
            # In case of an error while parsing the date, return None
            return None

    # If no explicit "Deadline" is found, try finding dates using "by" or "before"
    fallback_date_match = re.search(r'by\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', notice_text, re.IGNORECASE)
    if fallback_date_match:
        fallback_deadline_str = fallback_date_match.group(1).strip()
        
        try:
            # Parse the fallback deadline date
            fallback_deadline = parser.parse(fallback_deadline_str, fuzzy=True).strftime("%Y-%m-%d")
            return fallback_deadline
        except (ValueError, TypeError):
            return None
    
    return None  # Return None if no deadline is found


def fetch_notices(sort_by="id", sort_order="asc", status_filter=None, actions_filter=None, deadline_filter=None, page=1, per_page=10):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Ensure sort_by has a valid value, defaulting to "id"
    if not sort_by:
        sort_by = "id"

    # Ensure sort_order is valid, defaulting to "ASC"
    sort_order = sort_order.upper() if sort_order.lower() in ["asc", "desc"] else "ASC"

    # Base query to fetch notices
    query = "SELECT * FROM notices"
    conditions = []

    # Apply status filter if provided
    if status_filter:
        conditions.append(f"status='{status_filter}'")
    
    # Apply actions filter if provided
    if actions_filter:
        conditions.append(f"actions='{actions_filter}'")
    
    # Apply deadline filter if provided
    if deadline_filter == "upcoming":
        today = datetime.now().strftime("%Y-%m-%d")
        upcoming_deadline = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        conditions.append(f"DATE(deadline) <= DATE('{upcoming_deadline}') AND DATE(deadline) >= DATE('{today}')")

    # If there are conditions, add them to the query
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Apply sorting (use the validated sort_by and sort_order)
    query += f" ORDER BY {sort_by} {sort_order}"

    # Apply pagination
    offset = (page - 1) * per_page
    query += f" LIMIT {per_page} OFFSET {offset}"

    # Execute the query and fetch the notices
    cursor.execute(query)
    notices = cursor.fetchall()

    # Count total notices for pagination
    count_query = "SELECT COUNT(*) FROM notices"
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    cursor.execute(count_query)
    total_notices = cursor.fetchone()[0]
    
    conn.close()

    # Calculate total pages
    total_pages = (total_notices + per_page - 1) // per_page
    
    return notices, total_pages




def fetch_monitoring_data(page=1, per_page=10):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    offset = (page - 1) * per_page

    # Fetch the last notices with pagination
    cursor.execute("SELECT id, status, created_at FROM notices ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset))
    notices = cursor.fetchall()

    # Count total notices for pagination
    cursor.execute("SELECT COUNT(*) FROM notices")
    total_notices = cursor.fetchone()[0]
    
    conn.close()

    total_pages = (total_notices + per_page - 1) // per_page
    return notices, total_pages


# Calculate compliance metrics
def calculate_compliance_metrics():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notices")
    total_notices = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Completed'")
    completed_notices = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Error' OR status='Deadline Missed'")
    error_notices = cursor.fetchone()[0]

    compliance_rate = (completed_notices / total_notices) * 100 if total_notices > 0 else 0
    compliance_rate = round(compliance_rate, 2)

    error_rate = (error_notices / total_notices) * 100 if total_notices > 0 else 0
    error_rate = round(error_rate, 2)

    processing_time = 5  # Example value, implement logic if tracking time
    
    conn.close()
    return compliance_rate, processing_time, error_rate



@app.route('/api/notices')
def get_notices():
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'asc')
    status_filter = request.args.get('status_filter')
    actions_filter = request.args.get('actions_filter')
    deadline_filter = request.args.get('deadline_filter')
    page = int(request.args.get('page', 1))  # Pagination
    per_page = 10  # Number of records per page

    # Fetch notices and total pages
    notices, total_pages = fetch_notices(sort_by, sort_order, status_filter, actions_filter, deadline_filter, page, per_page)

    # Return notices and total pages as JSON for the frontend
    return jsonify({
        'notices': notices,
        'total_pages': total_pages,
        'current_page': page
    })



# API endpoints for chart data
@app.route('/api/compliance_data')
def compliance_data():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Completed'")
    completed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Pending'")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Error'")
    error = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notices WHERE status='Deadline Missed'")
    deadline_missed = cursor.fetchone()[0]

    conn.close()
    return jsonify(completed=completed, pending=pending, error=error, deadline_missed=deadline_missed)

@app.route('/api/compliance_timeline')
def compliance_timeline():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch the number of notices grouped by creation date
    cursor.execute("SELECT DATE(created_at), COUNT(*) FROM notices GROUP BY DATE(created_at)")
    rows = cursor.fetchall()

    # Handle None values before parsing dates
    dates = []
    counts = []

    for row in rows:
        if row[0]:  # Only process non-None date values
            date_str = datetime.strptime(row[0], '%Y-%m-%d').strftime('%d-%b-%y')
            dates.append(date_str)
            counts.append(row[1])
        else:
            print("Warning: Encountered a None date in the database.")

    conn.close()
    return jsonify(dates=dates, counts=counts)



@app.route('/mark_completed/<int:notice_id>', methods=['POST'])
def mark_completed(notice_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("UPDATE notices SET status = 'Completed' WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_notice():
    if 'file' not in request.files:
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)

    if file:
        notice_text = file.read().decode('utf-8')  # Assuming it's a text-based file

        # Summarize the notice
        summary = summarize_notice(notice_text)

        # Extract actions using AI (keyword-based)
        actions = extract_actions(notice_text)

        # Detect deadline using the new detect_deadline function
        deadline = detect_deadline(notice_text)

        # Generate a template response
        response_template = f"Dear Regulator, \n\nWe acknowledge receipt of your notice regarding:\n\nSummary: {summary}\n\nActions:\n{actions}\n\nThe deadline for compliance is: {deadline if deadline else 'None'}"

        # Store in the database
        store_notice(notice_text, summary, actions, response_template, deadline)

        # Send email to stakeholder (sample)
        return redirect(url_for('dashboard'))


    

@app.route('/send_sample_email')
def send_email_route():
    send_sample_email()
    # Update deadline status
    update_deadline_status()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'desc')  # Default to descending order
    status_filter = request.args.get('status_filter')
    actions_filter = request.args.get('actions_filter')
    deadline_filter = request.args.get('deadline_filter')
    page = int(request.args.get('page', 1))
    per_page = 10

    monitoring_page = int(request.args.get('monitoring_page', 1))

    # Update deadline status before fetching notices
    update_deadline_status()

    # Fetch notices and total pages
    notices, total_pages = fetch_notices(sort_by, sort_order, status_filter, actions_filter, deadline_filter, page, per_page)

    # Calculate overview metrics
    compliance_rate, processing_time, error_rate = calculate_compliance_metrics()

    # Fetch monitoring data
    monitoring_data, monitoring_total_pages = fetch_monitoring_data(monitoring_page, per_page)

    # Sort notices by the last updated field in descending order
    sorted_notices = sorted(notices, key=lambda x: (x[6] is not None, x[6] if x[6] is not None else ''), reverse=True)

    # Print sorted notices to verify
    print("Sorted Notices:", sorted_notices)

    return render_template('dashboard.html',
                           notices=sorted_notices,
                           compliance_rate=compliance_rate,
                           processing_time=processing_time,
                           error_rate=error_rate,
                           monitoring_data=monitoring_data,
                           page=page, total_pages=total_pages,
                           monitoring_page=monitoring_page, monitoring_total_pages=monitoring_total_pages,
                           sort_by=sort_by, sort_order=sort_order,
                           status_filter=status_filter, actions_filter=actions_filter, deadline_filter=deadline_filter)

if __name__ == '__main__':
    init_db()  # Initialize database
    app.run(debug=True)
