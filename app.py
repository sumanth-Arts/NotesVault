from flask import Flask, render_template, request, redirect, send_from_directory, session, url_for
import os
import sqlite3
from datetime import datetime
from datetime import timedelta
import uuid
from flask import send_file



app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
IMAGE_FOLDER = os.path.join("static", "images")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
app.secret_key = os.getenv("SECRET_KEY")

semesters = [f"Semester {i}" for i in range(1, 9)]


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin/dashboard")

        return "<h3>Invalid credentials</h3>"

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin_logged_in" not in session:
        return redirect("/admin")

    return render_template("admin_dashboard.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin")


@app.route("/admin/add-announcement", methods=["GET", "POST"])
def add_announcement():
    if "admin_logged_in" not in session:
        return redirect("/admin")
    if request.method == "POST":
        conn = sqlite3.connect("notes.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO announcements (title, message)
            VALUES (?, ?)
        """, (request.form["title"], request.form["message"]))

        conn.commit()
        conn.close()

        return redirect("/admin/dashboard")

    return render_template("add_announcement.html")


@app.route("/admin/add-topic", methods=["GET", "POST"])
def add_topic():
    if "admin_logged_in" not in session:
        return redirect("/admin")

    if request.method == "POST":
        semester = request.form["semester"]
        subject = request.form["subject"]
        unit = request.form["unit"]
        title = request.form["title"]
        summary = request.form["summary"]
        definition = request.form["definition"]
        example = request.form["example"]

        # Handle main topic image
        image = request.files.get("image")
        image_path = ""
        if image and image.filename != "":
            filename = str(uuid.uuid4()) + "_" + image.filename
            image_path = f"images/{filename}"
            image.save(os.path.join(IMAGE_FOLDER, filename))

        # Get lists for sections
        section_titles = request.form.getlist("section_title[]")
        section_contents = request.form.getlist("section_content[]")
        section_images = request.files.getlist("section_image[]")

        conn = sqlite3.connect("notes.db")
        try:
            cursor = conn.cursor()

            # 1. Insert into notes table
            cursor.execute("""
                INSERT INTO notes (semester, subject, unit, topic, content, definition, example, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (semester, subject, unit, title, summary, definition, example, image_path))

            topic_id = cursor.lastrowid

            # 2. Insert sections in the SAME transaction
            for i in range(len(section_titles)):
                sec_img_path = ""
                if i < len(section_images) and section_images[i].filename != "":
                    filename = str(uuid.uuid4()) + "_" + section_images[i].filename
                    sec_img_path = f"images/{filename}"
                    section_images[i].save(os.path.join(IMAGE_FOLDER, filename))

                cursor.execute("""
                    INSERT INTO topic_sections (topic_id, section_title, section_content, image_path, section_order)
                    VALUES (?, ?, ?, ?, ?)
                """, (topic_id, section_titles[i], section_contents[i], sec_img_path, i))

# ... (Inside your add_topic try block, after inserting sections) ...

        # 3. Insert Problems into problem_bank
            problems = request.form.getlist("problem[]")
            solutions = request.form.getlist("solution[]")

            for i in range(len(problems)):
                if problems[i].strip():  # Only insert if problem text exists
                    cursor.execute("""
                        INSERT INTO problem_bank (topic_id, problem, solution, problem_order)
                        VALUES (?, ?, ?, ?)
                    """, (topic_id, problems[i], solutions[i], i))

            conn.commit()
        except Exception as e:
            print(f"Error during POST: {e}")
            conn.rollback()
        finally:
            conn.close()

        return redirect("/admin/dashboard")

    # --- GET REQUEST LOGIC (Loading the form) ---
    # This only runs if the method is NOT POST
    conn = sqlite3.connect("notes.db")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT semester, subject FROM notes")
        subjects = cursor.fetchall()

        cursor.execute("SELECT DISTINCT semester, subject, unit FROM notes")
        units = cursor.fetchall()
    except Exception as e:
        print(f"Error during GET: {e}")
        subjects, units = [], []
    finally:
        conn.close()

    return render_template("add_topic.html",
                           semesters=semesters,
                           subjects=subjects,
                           units=units)


@app.route("/")
def home():
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, message, created_at
        FROM announcements
        ORDER BY created_at DESC
        LIMIT 10
    """)

    announcements = cursor.fetchall()

    formatted_announcements = []

    for title, message, created_at in announcements:
        if created_at:
            utc_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            ist_time = utc_time + timedelta(hours=5, minutes=30)

            created_at = ist_time.strftime("%d %b %Y, %I:%M %p")

        formatted_announcements.append((title, message, created_at))
    conn.close()

    return render_template("home.html",
                           semesters=semesters,
                           announcements=formatted_announcements)


@app.route("/semester/<semester_name>")
def semester(semester_name):
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT subject FROM notes WHERE semester=?", (semester_name,))
    subjects = cursor.fetchall()


    conn.close()

    return render_template("semester.html",
                           semester_name=semester_name,
                           subjects=[row[0] for row in subjects])


@app.route("/subject/<semester_name>/<subject_name>")
def subject(semester_name, subject_name):
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    # get all units
    cursor.execute("""
        SELECT DISTINCT unit
        FROM notes
        WHERE semester=? AND subject=?
        ORDER BY CAST(SUBSTR(unit, 6) AS INTEGER)
    """, (semester_name, subject_name))

    units = [row[0] for row in cursor.fetchall()]

    # get selected unit
    selected_unit = request.args.get("unit")

    # if no unit → default to first
    if not selected_unit and units:
        selected_unit = units[0]

    # get topics for selected unit
    topics = []
    if selected_unit:
        cursor.execute("""
            SELECT id, topic, content, definition, example
            FROM notes
            WHERE semester=? AND subject=? AND unit=?
        """, (semester_name, subject_name, selected_unit))

        topics = cursor.fetchall()

    conn.close()

    return render_template("subject.html",
                           semester_name=semester_name,
                           subject_name=subject_name,
                           units=units,
                           selected_unit=selected_unit,
                           topics=topics)


@app.route("/unit_content/<semester>/<subject>/<unit>")
def notes(semester, subject, unit):
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, topic, content, definition, example, image_path
        FROM notes
        WHERE semester=? AND subject=? AND unit=?
        ORDER BY topic_order ASC
    """, (semester, subject, unit))

    topics = cursor.fetchall()

    topic_data = []

    for topic in topics:
        cursor.execute("""
            SELECT section_title, section_content, image_path
            FROM topic_sections
            WHERE topic_id=?
            ORDER BY section_order
        """, (topic[0],))

        sections = cursor.fetchall()

        cursor.execute("""
            SELECT problem, solution
            FROM problem_bank
            WHERE topic_id=?
            ORDER BY problem_order
        """, (topic[0],))

        problems = cursor.fetchall()

        topic_data.append({
            "id": topic[0],
            "title": topic[1],
            "summary": topic[2],
            "definition": topic[3],
            "example": topic[4],
            "image": topic[5],
            "sections": sections,
            "problems": problems
        })

    conn.close()

    return render_template("notes.html",
                           semester_name=semester,
                           subject_name=subject,
                           unit_name=unit,
                           content=topic_data)


@app.route("/resource/<semester>/<subject>/<unit>/<rtype>")
def load_resource(semester, subject, unit, rtype):
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_path FROM resources
        WHERE semester=? AND subject=? AND unit=? AND type=?
    """, (semester, subject, unit, rtype))

    result = cursor.fetchone()
    conn.close()

    if not result:
        return "<div style='padding:40px; color:white;'><h2>will be  uploaded soon!!</h2></div>"

    file_path = result[0]
    
    # CSS to make the container look perfect in fullscreen mode
    fullscreen_style = """
    <style>
        #resource-container:fullscreen {
            background: white;
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        #resource-container:fullscreen iframe {
            height: 100vh !important;
            border-radius: 0 !important;
        }
    </style>
    """

    # 1. Determine the header text using Python conditions
    if subject == "Design and Analysis" and unit == "Unit 4" and rtype == "qb":
        header_title = "Unit 3 and 4- QB"
    elif subject == "Cyber Security" and unit == "Unit 1" and rtype == "ppt":
        header_title = "Unit 1 and 2- Slides"
    elif subject == "Cyber Security" and unit == "Unit 3" and rtype == "ppt":
        header_title = "Unit 3 and 4- Slides"
    else:
        header_title = f"{unit} - {rtype.upper()}"

    # 2. Drop the title cleanly inside the Python f-string
    top_bar = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <h2 style="color:white; font-size:24px; font-weight:bold;">{header_title}</h2>
        <button onclick="openFullscreen('resource-container')" 
                style="background:#0284c7; color:white; border:none; padding:10px 16px; border-radius:12px; cursor:pointer; font-weight:600;">
            Fullscreen
        </button>
    </div>
    """

    # Determine URL
    if file_path.startswith("http"):
        iframe_src = file_path
    elif file_path.lower().endswith(".pdf"):
        iframe_src = f"/uploads/{file_path}"
    else:
        base_url = request.host_url
        file_url = f"{base_url}uploads/{file_path}"
        iframe_src = f"https://docs.google.com/gview?url={file_url}&embedded=true"

    return f"""
    {fullscreen_style}
    <div class='card' style='padding:20px;'>
        {top_bar}
        <div id="resource-container" style="background:white; border-radius:16px; overflow:hidden;">
            <iframe src="{iframe_src}" width="100%" height="700px" style="border:none;"></iframe>
        </div>
    </div>
    """

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/admin/upload-resource", methods=["GET", "POST"])
def upload_resource():

    if "admin_logged_in" not in session:
        return redirect("/admin")

    if request.method == "POST":

        semester = request.form["semester"]
        subject = request.form["subject"]
        unit = request.form["unit"]
        rtype = request.form["type"]

        # Google Drive link
        resource_link = request.form["resource_link"].strip()

        # auto convert /view → /preview
        resource_link = resource_link.replace(
            "/view?usp=sharing",
            "/preview"
        )

        resource_link = resource_link.replace(
            "/view",
            "/preview"
        )

        conn = sqlite3.connect("notes.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO resources (
                semester,
                subject,
                unit,
                type,
                file_path
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            semester,
            subject,
            unit,
            rtype,
            resource_link
        ))

        conn.commit()
        conn.close()

        return redirect("/admin/dashboard")

    # GET REQUEST
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT semester, subject
        FROM notes
    """)
    subjects = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT semester, subject, unit
        FROM notes
    """)
    units = cursor.fetchall()

    conn.close()

    return render_template(
        "upload_resource.html",
        semesters=semesters,
        subjects=subjects,
        units=units
    )

@app.route("/admin/topics")
def admin_topics():
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, semester, subject, unit, topic
        FROM notes
        ORDER BY semester, subject, unit
    """)

    topics = cursor.fetchall()
    conn.close()

    return render_template("admin_topics.html", topics=topics)

@app.route("/admin/delete-topic/<int:topic_id>", methods=["POST"])
def delete_topic(topic_id):
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM topic_sections WHERE topic_id=?", (topic_id,))
    cursor.execute("DELETE FROM notes WHERE id=?", (topic_id,))

    conn.commit()
    conn.close()

    return redirect("/admin/topics")

@app.route("/admin/edit-topic/<int:topic_id>", methods=["GET", "POST"])
def edit_topic(topic_id):
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    if request.method == "POST":
        title = request.form["title"]
        summary = request.form["summary"]
        definition = request.form["definition"]
        example = request.form["example"]

 
        cursor.execute("SELECT image_path FROM notes WHERE id=?", (topic_id,))
        existing = cursor.fetchone()
        current_image = existing[0] if existing else ""

        remove_image = request.form.get("remove_image")
        new_image = request.files.get("image")

        image_path = current_image


        if remove_image:
            if current_image:
                old_path = os.path.join("static", current_image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            image_path = ""


        elif new_image and new_image.filename != "":
            filename = str(uuid.uuid4()) + "_" + new_image.filename
            image_path = f"images/{filename}"
            new_image.save(os.path.join("static", image_path))

        cursor.execute("""
            UPDATE notes
            SET topic=?, content=?, definition=?, example=?, image_path=?
            WHERE id=?
        """, (title, summary, definition, example, image_path, topic_id))

        cursor.execute("DELETE FROM topic_sections WHERE topic_id=?", (topic_id,))

        section_titles = request.form.getlist("section_title[]")
        section_contents = request.form.getlist("section_content[]")
        section_images = request.files.getlist("section_image[]")

        IMAGE_FOLDER = os.path.join("static", "images")

        for i in range(len(section_titles)):
            sec_img_path = ""

            if section_images[i] and section_images[i].filename != "":
                filename = str(uuid.uuid4()) + "_" + section_images[i].filename
                sec_img_path = f"images/{filename}"
                section_images[i].save(os.path.join(IMAGE_FOLDER, filename))

            cursor.execute("""
                INSERT INTO topic_sections (topic_id, section_title, section_content, image_path, section_order)
                VALUES (?, ?, ?, ?, ?)
            """, (topic_id, section_titles[i], section_contents[i], sec_img_path, i))
        
        # Update Problems
        problems = request.form.getlist("problem[]")
        solutions = request.form.getlist("solution[]")

        # Clear existing problems for this topic
        cursor.execute("DELETE FROM problem_bank WHERE topic_id=?", (topic_id,))

        # Re-insert updated problems
        for i in range(len(problems)):
            if problems[i].strip():
                cursor.execute("""
                    INSERT INTO problem_bank (topic_id, problem, solution, problem_order)
                    VALUES (?, ?, ?, ?)
                """, (topic_id, problems[i], solutions[i], i))

        conn.commit()
        conn.close()

        return redirect("/admin/topics")

 
    cursor.execute("""
        SELECT topic, content, definition, example, image_path
        FROM notes WHERE id=?
    """, (topic_id,))
    topic = cursor.fetchone()

    cursor.execute("""
        SELECT section_title, section_content, image_path
        FROM topic_sections
        WHERE topic_id=?
        ORDER BY section_order
    """, (topic_id,))
    sections = cursor.fetchall()

    cursor.execute("""
    SELECT problem, solution
    FROM problem_bank
    WHERE topic_id=?
    ORDER BY problem_order
""", (topic_id,))

    problems = cursor.fetchall()

    conn.close()

    return render_template("edit_topic.html",
                           topic=topic,
                           sections=sections,
                           problems=problems,
                           topic_id=topic_id)
@app.route("/admin/announcements")
def admin_announcements():
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, message, created_at
        FROM announcements
        ORDER BY created_at DESC
    """)

    announcements = cursor.fetchall()
    conn.close()

    return render_template("admin_announcements.html", announcements=announcements)


@app.route("/admin/delete-announcement/<int:aid>", methods=["POST"])
def delete_announcement(aid):
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM announcements WHERE id=?", (aid,))

    conn.commit()
    conn.close()

    return redirect("/admin/announcements")

@app.route("/admin/edit-announcement/<int:aid>", methods=["GET", "POST"])
def edit_announcement(aid):
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    if request.method == "POST":
        title = request.form["title"]
        message = request.form["message"]

        cursor.execute("""
            UPDATE announcements
            SET title=?, message=?
            WHERE id=?
        """, (title, message, aid))

        conn.commit()
        conn.close()

        return redirect("/admin/announcements")

    cursor.execute("""
        SELECT title, message FROM announcements WHERE id=?
    """, (aid,))
    announcement = cursor.fetchone()

    conn.close()

    return render_template("edit_announcements.html",
                           announcement=announcement,
                           aid=aid)



from flask import jsonify

@app.route("/admin/update-order", methods=["POST"])
def update_order():
    if "admin_logged_in" not in session:
        return redirect("/admin")
    data = request.get_json()

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    for item in data:
        cursor.execute("""
            UPDATE notes SET topic_order=?
            WHERE id=?
        """, (item["order"], item["id"]))

    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

@app.route("/admin/delete-resource/<int:rid>", methods=["POST"])
def delete_resource(rid):
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT file_path FROM resources WHERE id=?", (rid,))
    result = cursor.fetchone()

    if result:
        file_name = result[0]
        file_path = os.path.join("uploads", file_name)

        if os.path.exists(file_path):
            os.remove(file_path)

        cursor.execute("DELETE FROM resources WHERE id=?", (rid,))

    conn.commit()
    conn.close()

    return redirect("/admin/dashboard")
@app.route("/admin/resources")
def admin_resources():
    if "admin_logged_in" not in session:
        return redirect("/admin")
    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, semester, subject, unit, type, file_path
        FROM resources
    """)

    resources = cursor.fetchall()
    conn.close()

    return render_template("admin_resources.html", resources=resources)


@app.route("/search_suggestions")
def search_suggestions():
    query = request.args.get("q", "").lower()
    if not query:
        return {"results": []}

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    # Deep Scan Query: 
    # It finds the topic even if the query matches a sub-section title or content
    cursor.execute("""
        SELECT DISTINCT 
            n.semester, 
            n.subject, 
            n.unit, 
            n.topic
        FROM notes n
        LEFT JOIN topic_sections ts ON n.id = ts.topic_id
        WHERE LOWER(n.topic) LIKE ? 
           OR LOWER(ts.section_title) LIKE ? 
           OR LOWER(ts.section_content) LIKE ?
        LIMIT 6
    """, (f"%{query}%", f"%{query}%", f"%{query}%"))

    results = cursor.fetchall()
    conn.close()

    suggestions = []
    for sem, sub, unit, topic in results:
        suggestions.append({
            "semester": sem,
            "subject": sub,
            "unit": unit,
            "topic": topic
        })

    return {"results": suggestions}



@app.route("/admin/download-db")
def download_db():

    if "admin_logged_in" not in session:
        return redirect("/admin")

    return send_file(
        "notes.db",
        as_attachment=True
    )

@app.route("/submit-feedback", methods=["POST"])
def submit_feedback():

    name = request.form.get("name")
    subject = request.form.get("subject")
    issue_type = request.form.get("issue_type")
    message = request.form.get("message")

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO feedback (
            name,
            subject,
            issue_type,
            message
        )
        VALUES (?, ?, ?, ?)
    """, (
        name,
        subject,
        issue_type,
        message
    ))

    conn.commit()
    conn.close()

    return redirect(request.referrer)
@app.route("/admin/feedback")
def admin_feedback():

    if "admin_logged_in" not in session:
        return redirect("/admin")

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, subject, issue_type, message, created_at
        FROM feedback
        ORDER BY created_at DESC
    """)

    feedbacks = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_feedback.html",
        feedbacks=feedbacks
    )


if __name__ == "__main__":
    app.run()