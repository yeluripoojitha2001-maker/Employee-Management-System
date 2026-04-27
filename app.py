from flask import Flask, render_template, request, redirect, session, flash, url_for, make_response
import sqlite3
import datetime
import os
import csv
import qrcode
from io import TextIOWrapper, StringIO, BytesIO
from werkzeug.utils import secure_filename

# PDF library setup
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ImportError:
    print("ReportLab missing!")

app = Flask(__name__)
app.secret_key = "123"

# --- 📂 CONFIGURATION ---
UPLOAD_FOLDER = 'static/uploads'
QR_FOLDER = 'static/qrcodes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
DATABASE = "ems.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, dob TEXT, phone TEXT, address TEXT, qualification TEXT, skills TEXT, bio TEXT, photo TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, status TEXT, UNIQUE(username, date))')
    conn.execute('CREATE TABLE IF NOT EXISTS leaves (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, from_date TEXT, to_date TEXT, reason TEXT, status TEXT DEFAULT "Pending")')
    conn.execute('CREATE TABLE IF NOT EXISTS punch_status (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, punch_in TEXT, punch_out TEXT, work_hours TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS work_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, date TEXT, task TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS salary (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, month TEXT, basic REAL, bonus REAL, deduction REAL, net_salary REAL, UNIQUE(username, month))')
    conn.execute('CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, message TEXT, created_at TEXT)')
    
    conn.commit()
    conn.close()

init_db()

# ==========================================================
# 🔐 MODULE 1: AUTHENTICATION
# ==========================================================

@app.route("/")
def home():
    return render_template("auth/login.html")

@app.route("/register_page")
def register_page():
    return render_template("auth/user_register.html")

@app.route("/register", methods=["POST"])
def register():
    u = request.form.get("username").strip().lower()
    p = request.form.get("password")

    if u == "admin":
        flash("Unauthorized! ❌")
        return redirect(url_for("register_page"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO employees (username, password, role) VALUES (?, ?, ?)",
            (u, p, "employee")
        )
        conn.commit()
        flash("Employee registered successfully!")
        return redirect(url_for("home"))
    except:
        flash("Username already exists!")
        return redirect(url_for("register_page"))
    finally:
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    u = request.form.get("username").strip().lower()
    p = request.form.get("password")
    r = request.form.get("role")

    # Admin login
    if u == "admin" and p == "admin123":
        session["user"] = "admin"
        session["role"] = "admin"
        flash("Admin login successful!")
        return redirect(url_for("admin_dashboard"))

    # Employee login
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM employees WHERE username=? AND password=? AND role=?",
        (u, p, r)
    ).fetchone()
    conn.close()

    if user:
        session["user"] = user["username"]
        session["role"] = user["role"]
        flash("Employee login successful!")
        return redirect(url_for("employee_dashboard"))

    flash("Invalid username or password!")
    return redirect(url_for("home"))

# ==========================================================
# 🕒 MODULE 2: EMPLOYEE DASHBOARD & FEATURES
# ==========================================================

@app.route("/employee_dashboard")
def employee_dashboard():
    if "user" not in session:
        return redirect("/")

    if session.get("role") != "employee":
        return redirect(url_for("admin_dashboard"))

    u = session.get("user")
    today = str(datetime.date.today())

    conn = get_db()
    status_row = conn.execute(
        "SELECT status FROM attendance WHERE username=? AND date=?",
        (u, today)
    ).fetchone()
    qr_url = url_for('static', filename=f'qrcodes/qr_{u}.png')
    conn.close()

    return render_template("employee/employee_dashboard.html", present=status_row, qr_path=qr_url)

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    if "user" not in session:
        return redirect("/")

    u = session['user']
    today = str(datetime.date.today())
    conn = get_db()

    try:
        conn.execute("INSERT INTO attendance (username, date, status) VALUES (?, ?, ?)", (u, today, "Present"))
        conn.commit()
        flash("Attendance Marked! ✅")
    except:
        flash("Already Marked Today! ⚠️")
    finally:
        conn.close()

    return redirect(url_for("employee_dashboard"))

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect("/")

    if session.get("role") != "employee":
        return redirect(url_for("admin_dashboard"))

    u = session['user']
    conn = get_db()

    if request.method == "POST":
        f = request.files.get("photo")
        if f and f.filename != '':
            fname = secure_filename(f"{u}.jpg")
            f.save(os.path.join(UPLOAD_FOLDER, fname))
            conn.execute("UPDATE employees SET photo=? WHERE username=?", (fname, u))

        d = request.form
        conn.execute(
            "UPDATE employees SET dob=?, phone=?, address=?, qualification=?, skills=?, bio=? WHERE username=?",
            (d.get('dob'), d.get('phone'), d.get('address'), d.get('qualification'), d.get('skills'), d.get('bio'), u)
        )
        conn.commit()
        flash("Profile Updated! ✅")

    qr_link = f"http://10.219.76.31:5000/mark_attendance_qr/{u}"
    qrcode.make(qr_link).save(os.path.join(QR_FOLDER, f"qr_{u}.png"))

    emp = conn.execute("SELECT * FROM employees WHERE username=?", (u,)).fetchone()
    conn.close()

    return render_template("employee/profile.html", employee=emp, qr_path=url_for('static', filename=f'qrcodes/qr_{u}.png'))

@app.route("/work_tracker", methods=["GET", "POST"])
def work_tracker():
    if "user" not in session:
        return redirect("/")

    today_disp = datetime.date.today().strftime("%d-%m-%Y")

    if request.method == "POST":
        u = session['user']
        task = request.form.get("task")
        today_db = str(datetime.date.today())

        conn = get_db()
        conn.execute("INSERT INTO work_reports (username, date, task) VALUES (?, ?, ?)", (u, today_db, task))
        conn.commit()
        conn.close()

        flash("Work Submitted! ✅")
        return redirect(url_for("employee_dashboard"))

    return render_template("work_tracker.html", now_date=today_disp)

@app.route("/punch_system")
def punch_system():
    if "user" not in session:
        return redirect("/")

    recs = get_db().execute("SELECT * FROM punch_status WHERE username=? ORDER BY id DESC", (session['user'],)).fetchall()
    return render_template("employee/punch_status.html", records=recs)

@app.route("/punch_in", methods=["POST"])
def punch_in():
    if "user" not in session:
        return redirect("/")

    u = session['user']
    today = str(datetime.date.today())
    now_t = datetime.datetime.now().strftime("%H:%M:%S")

    conn = get_db()
    check = conn.execute("SELECT * FROM punch_status WHERE username=? AND date=? AND punch_out IS NULL", (u, today)).fetchone()

    if not check:
        conn.execute("INSERT INTO punch_status (username, date, punch_in) VALUES (?, ?, ?)", (u, today, now_t))
        conn.commit()
        flash("Punched IN! 🕒")
    else:
        flash("Already Punched IN Today! ⚠️")

    conn.close()
    return redirect(url_for("punch_system"))

@app.route("/punch_out", methods=["POST"])
def punch_out():
    if "user" not in session:
        return redirect("/")

    u = session['user']
    today = str(datetime.date.today())
    now_t = datetime.datetime.now().strftime("%H:%M:%S")

    conn = get_db()
    row = conn.execute("SELECT * FROM punch_status WHERE username=? AND date=? AND punch_out IS NULL", (u, today)).fetchone()

    if row:
        t1 = datetime.datetime.strptime(row['punch_in'], "%H:%M:%S")
        t2 = datetime.datetime.strptime(now_t, "%H:%M:%S")
        hrs = round((t2 - t1).total_seconds() / 3600, 2)

        conn.execute("UPDATE punch_status SET punch_out=?, work_hours=? WHERE id=?", (now_t, str(hrs), row['id']))
        conn.commit()
        flash("Punched OUT! 👋")
    else:
        flash("No active Punch IN found! ⚠️")

    conn.close()
    return redirect(url_for("punch_system"))

@app.route("/attendance_history")
def attendance_history():
    if "user" not in session:
        return redirect("/")

    u = session['user']
    d_f = request.args.get('date', '')

    query = "SELECT * FROM attendance WHERE username = ?"
    params = [u]

    if d_f:
        query += " AND date = ?"
        params.append(d_f)

    records = get_db().execute(query + " ORDER BY date DESC", params).fetchall()
    return render_template("employee/attendance_history.html", records=records)

# ==========================================================
# 👑 MODULE 3: ADMIN DASHBOARD & MANAGEMENT
# ==========================================================

@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM employees WHERE role='employee'").fetchone()[0]
    present = conn.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (str(datetime.date.today()),)).fetchone()[0]
    conn.close()

    return render_template("admin/admin_dashboard.html", total=total, present=present)

@app.route("/admin_attendance_view")
@app.route("/attendance")
def admin_attendance_view():
    if session.get("role") != "admin":
        return redirect("/")

    n = request.args.get('name', '')
    s = request.args.get('status', 'All')
    d = request.args.get('date', '')

    query = "SELECT * FROM attendance WHERE 1=1"
    params = []

    if n:
        query += " AND username LIKE ?"
        params.append(f"%{n}%")
    if s != 'All':
        query += " AND status = ?"
        params.append(s)
    if d:
        query += " AND date = ?"
        params.append(d)

    recs = get_db().execute(query + " ORDER BY id DESC", params).fetchall()
    return render_template("admin/attendance_manage.html", records=recs)

@app.route("/upload_attendance", methods=["POST"])
def upload_attendance():
    if session.get("role") != "admin":
        return redirect("/")

    file = request.files.get("file")
    if file and file.filename.endswith('.csv'):
        csv_f = TextIOWrapper(file, encoding='utf-8')
        reader = csv.reader(csv_f)
        next(reader, None)

        conn = get_db()
        p, a = 0, 0

        for row in reader:
            if len(row) >= 3:
                conn.execute("INSERT OR REPLACE INTO attendance (username, date, status) VALUES (?, ?, ?)", (row[0], row[1], row[2]))
                if row[2].strip().lower() == 'present':
                    p += 1
                else:
                    a += 1

        conn.commit()
        conn.close()
        flash(f"CSV uploaded successfully! Total: {p+a}, Present: {p}, Absent: {a} ✅")
    else:
        flash("Please upload a valid CSV file! ❌")

    return redirect(url_for("admin_attendance_view"))

@app.route("/admin_mark_attendance", methods=["GET", "POST"])
def admin_mark_attendance():
    if session.get("role") != "admin":
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        date = request.form.get("date", "").strip()
        status = request.form.get("status", "").strip()
    else:
        username = request.args.get("username", "").strip().lower()
        date = request.args.get("date", "").strip()
        status = request.args.get("status", "").strip()

    if not username or not date or not status:
        flash("Please fill all fields! ❌")
        return redirect(url_for("admin_attendance_view"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO attendance (username, date, status) VALUES (?, ?, ?)",
            (username, date, status)
        )
        conn.commit()
        flash(f"{username.capitalize()} marked as {status} on {date} ✅")
    except Exception as e:
        flash(f"Error: {e}")
    finally:
        conn.close()

    return redirect(url_for("admin_attendance_view"))

@app.route("/download_pdf")
def download_pdf():
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()
    recs = conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    y = 750

    p.drawString(100, y, "Attendance Report")
    y -= 30

    for r in recs:
        p.drawString(100, y, f"{r['username']} - {r['date']} - {r['status']}")
        y -= 20
        if y < 50:
            p.showPage()
            y = 750

    p.save()
    buffer.seek(0)
    return make_response(buffer.getvalue(), 200, {"Content-type": "application/pdf"})

@app.route("/admin_leaves")
def admin_leaves():
    if session.get("role") != "admin":
        return redirect("/")

    data = get_db().execute("SELECT * FROM leaves ORDER BY id DESC").fetchall()
    return render_template("admin/leave_manage.html", data=data)

@app.route("/approve_leave/<int:id>")
def approve_leave(id):
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()
    conn.execute("UPDATE leaves SET status='Approved' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Leave Approved! ✅")
    return redirect(url_for("admin_leaves"))

@app.route("/reject_leave/<int:id>")
def reject_leave(id):
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()
    conn.execute("UPDATE leaves SET status='Rejected' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Leave Rejected! ❌")
    return redirect(url_for("admin_leaves"))

@app.route("/admin_punch_status")
def admin_punch_status():
    if session.get("role") != "admin":
        return redirect("/")

    u = request.args.get('username', '').strip()
    d = request.args.get('date', '').strip()

    query = "SELECT * FROM punch_status WHERE 1=1"
    params = []

    if u:
        query += " AND LOWER(username) LIKE ?"
        params.append(f"%{u.lower()}%")

    if d:
        query += " AND date = ?"
        params.append(d)

    data = get_db().execute(query + " ORDER BY id DESC", params).fetchall()
    return render_template("admin/punch_status.html", data=data)

@app.route("/admin_work_reports")
def admin_work_reports():
    if session.get("role") != "admin":
        return redirect("/")

    u = request.args.get('username', '')
    d = request.args.get('date', '')

    query = "SELECT * FROM work_reports WHERE 1=1"
    params = []

    if u:
        query += " AND username LIKE ?"
        params.append(f"%{u}%")
    if d:
        query += " AND date = ?"
        params.append(d)

    reports = get_db().execute(query + " ORDER BY id DESC", params).fetchall()
    return render_template("admin/work_report_admin.html", reports=reports)

@app.route("/admin_profiles")
def admin_profiles():
    if session.get("role") != "admin":
        return redirect("/")

    users = get_db().execute("SELECT * FROM employees WHERE role='employee'").fetchall()
    return render_template("admin/admin_profiles.html", employees=users)

# 🔴 DELETE USER ROUTE – ADD THIS BELOW
@app.route("/delete_user/<int:id>")
def delete_user(id):
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()

    user = conn.execute("SELECT username FROM employees WHERE id=?", (id,)).fetchone()
    if user:
        username = user["username"]

        conn.execute("DELETE FROM attendance WHERE username=?", (username,))
        conn.execute("DELETE FROM punch_status WHERE username=?", (username,))
        conn.execute("DELETE FROM leaves WHERE username=?", (username,))
        conn.execute("DELETE FROM work_reports WHERE username=?", (username,))
        conn.execute("DELETE FROM salary WHERE username=?", (username,))

    conn.execute("DELETE FROM employees WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("User Deleted Successfully 🗑️")
    return redirect(url_for("admin_profiles"))


# ==========================================================
# 📢 NOTICE BOARD MODULE
# ==========================================================

@app.route("/admin_notice_board", methods=["GET", "POST"])
def admin_notice_board():
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()

    if request.method == "POST":
        title = request.form.get("title")
        message = request.form.get("message")
        created_at = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

        conn.execute(
            "INSERT INTO notices (title, message, created_at) VALUES (?, ?, ?)",
            (title, message, created_at)
        )
        conn.commit()
        flash("Notice Added Successfully! 📢")

    notices = conn.execute("SELECT * FROM notices ORDER BY id DESC").fetchall()
    conn.close()

    return render_template("admin/notice_board.html", notices=notices)


@app.route("/delete_notice/<int:id>")
def delete_notice(id):
    if session.get("role") != "admin":
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM notices WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Notice Deleted! 🗑️")
    return redirect(url_for("admin_notice_board"))


@app.route("/employee_notice_board")
def employee_notice_board():
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    notices = conn.execute("SELECT * FROM notices ORDER BY id DESC").fetchall()
    conn.close()

    return render_template("employee/notice_board.html", notices=notices)

# ================= SALARY MODULE =================

@app.route("/admin_salary_manage")
def admin_salary_manage():
    if session.get("role") != "admin":
        return redirect("/")

    records = get_db().execute("SELECT * FROM salary ORDER BY id DESC").fetchall()
    return render_template("admin/salary_manage.html", records=records)

@app.route("/save_salary", methods=["POST"])
def save_salary():
    if session.get("role") != "admin":
        return redirect("/")

    username = request.form.get("username", "").strip().lower()
    month = request.form.get("month", "")
    basic = float(request.form.get("basic", 0) or 0)
    bonus = float(request.form.get("bonus", 0) or 0)
    deduction = float(request.form.get("deduction", 0) or 0)

    net_salary = basic + bonus - deduction

    conn = get_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO salary (username, month, basic, bonus, deduction, net_salary)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, month, basic, bonus, deduction, net_salary))
        conn.commit()
        flash(f"Salary saved for {username.capitalize()} - {month} ✅")
    except Exception as e:
        flash(f"Error: {e}")
    finally:
        conn.close()

    return redirect(url_for("admin_salary_manage"))

@app.route("/upload_salary", methods=["POST"])
def upload_salary():
    if session.get("role") != "admin":
        return redirect("/")

    file = request.files.get("file")

    if file and file.filename.endswith('.csv'):
        csv_f = TextIOWrapper(file, encoding='utf-8')
        reader = csv.reader(csv_f)
        next(reader, None)

        conn = get_db()
        count = 0

        for row in reader:
            if len(row) >= 5:
                username = row[0].strip().lower()
                month = row[1].strip()
                basic = float(row[2])
                bonus = float(row[3])
                deduction = float(row[4])

                net_salary = basic + bonus - deduction

                conn.execute("""
                    INSERT OR REPLACE INTO salary 
                    (username, month, basic, bonus, deduction, net_salary)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, month, basic, bonus, deduction, net_salary))

                count += 1

        conn.commit()
        conn.close()

        flash(f"Salary CSV uploaded successfully! {count} records added ✅")
    else:
        flash("Please upload a valid CSV file! ❌")

    return redirect(url_for("admin_salary_manage"))

@app.route("/my_salary")
def my_salary():
    if "user" not in session:
        return redirect("/")

    user = session["user"]

    records = get_db().execute(
        "SELECT * FROM salary WHERE username=? ORDER BY id DESC",
        (user,)
    ).fetchall()

    return render_template("employee/my_salary.html", records=records)



# ==========================================================
# ⚙️ EXTRA LOGIC (Leaves, QR, Export)
# ==========================================================

@app.route("/apply_leave", methods=["GET", "POST"])
def apply_leave():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        u = session['user']
        f = request.form.get("from_date")
        t = request.form.get("to_date")
        r = request.form.get("reason")

        conn = get_db()
        conn.execute("INSERT INTO leaves (username, from_date, to_date, reason) VALUES (?, ?, ?, ?)", (u, f, t, r))
        conn.commit()
        conn.close()

        flash("Leave Applied! ✅")
        return redirect(url_for("my_leaves"))

    return render_template("employee/apply_leave.html")

@app.route("/my_leaves")
def my_leaves():
    if "user" not in session:
        return redirect("/")

    data = get_db().execute("SELECT * FROM leaves WHERE username=? ORDER BY id DESC", (session['user'],)).fetchall()
    return render_template("employee/my_leaves.html", data=data)

@app.route("/delete_leave/<int:id>")
def delete_leave(id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    conn.execute("DELETE FROM leaves WHERE id=? AND username=? AND status='Pending'", (id, session['user']))
    conn.commit()
    conn.close()

    flash("Deleted! 🗑️")
    return redirect(url_for("my_leaves"))

@app.route("/mark_attendance_qr/<username>")
def mark_attendance_qr(username):
    today = str(datetime.date.today())
    now_t = datetime.datetime.now().strftime("%H:%M:%S")

    conn = get_db()
    try:
        conn.execute("INSERT INTO attendance (username, date, status) VALUES (?, ?, ?)", (username, today, "Present"))
        conn.commit()
        res = "Success! ✅"
    except:
        res = "Already Marked! ⚠️"
    finally:
        conn.close()

    return f"<div style='text-align:center;padding:50px;'><h1>{res}</h1><p>User: {username}<br>Date: {today}<br>Time: {now_t}</p></div>"

@app.route("/export_attendance")
def export_attendance():
    if session.get("role") != "admin":
        return redirect("/")

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Username', 'Date', 'Status'])

    for r in get_db().execute("SELECT username, date, status FROM attendance").fetchall():
        cw.writerow([r[0], r[1], r[2]])

    res = make_response(si.getvalue())
    res.headers["Content-Disposition"] = "attachment; filename=report.csv"
    res.headers["Content-type"] = "text/csv"
    return res

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)