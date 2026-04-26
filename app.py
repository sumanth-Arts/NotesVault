from flask import Flask, render_template, request, redirect, send_from_directory, session, url_for
import os
import sqlite3
from datetime import datetime
from datetime import timedelta
import uuid
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

        image = request.files["image"]
        image_path = ""

        if image and image.filename != "":
            filename = str(uuid.uuid4()) + "_" + image.filename
            image_path = f"images/{filename}"
            image.save(os.path.join(IMAGE_FOLDER, filename))

        conn = sqlite3.connect("notes.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO notes (semester, subject, unit, topic, content, definition, example, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (semester, subject, unit, title, summary, definition, example, image_path))

        topic_id = cursor.lastrowid

    section_titles = request.form.getlist("section_title[]")
    section_contents = request.form.getlist("section_content[]")
    section_images = request.files.getlist("section_image[]")
    existing_images = request.form.getlist("existing_section_image[]")
    remove_flags = request.form.getlist("remove_section_image[]")

    IMAGE_FOLDER = os.path.join("static", "images")

    for i in range(len(section_titles)):
        sec_img_path = existing_images[i] if i < len(existing_images) else ""

        remove_flag = False
        if i < len(remove_flags):
            remove_flag = remove_flags[i] == "on"

        if remove_flag and sec_img_path:
            old_path = os.path.join("static", sec_img_path)
            if os.path.exists(old_path):
                os.remove(old_path)
            sec_img_path = ""

        elif section_images[i] and section_images[i].filename != "":
            filename = str(uuid.uuid4()) + "_" + section_images[i].filename
            sec_img_path = f"images/{filename}"
            section_images[i].save(os.path.join(IMAGE_FOLDER, filename))

        cursor.execute("""
            INSERT INTO topic_sections (topic_id, section_title, section_content, image_path, section_order)
            VALUES (?, ?, ?, ?, ?)
        """, (topic_id, section_titles[i], section_contents[i], sec_img_path, i))

        conn.commit()
        conn.close()

        return redirect("/admin/dashboard")

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT semester, subject FROM notes")
    subjects = cursor.fetchall()

    cursor.execute("SELECT DISTINCT semester, subject, unit FROM notes")
    units = cursor.fetchall()

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

    cursor.execute("""
        SELECT DISTINCT unit
        FROM notes
        WHERE semester=? AND subject=?
        ORDER BY CAST(SUBSTR(unit, 6) AS INTEGER)
    """, (semester_name, subject_name))

    units = [row[0] for row in cursor.fetchall()]
    conn.close()

    return render_template("subject.html",
                           semester_name=semester_name,
                           subject_name=subject_name,
                           units=units)


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
        return "<h2>No resource found</h2>"

    file_name = result[0]

    base_url = request.host_url
    file_url = f"{base_url}uploads/{file_name}"

    if file_name.lower().endswith(".pdf"):
        return f"""
        <div class='card'>
            <h2>{unit} - {rtype.upper()}</h2>
            <iframe src='/uploads/{file_name}' width='100%' height='600px'></iframe>
        </div>
        """
    return f"""
    <div class='card'>
        <h2>{unit} - {rtype.upper()}</h2>
        <iframe src="https://docs.google.com/gview?url={file_url}&embedded=true"
                width="100%" height="600px"></iframe>
    </div>
    """


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if "admin_logged_in" not in session:
        return redirect("/admin")
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

        file = request.files["file"]

        if file and file.filename != "":
            filename = str(uuid.uuid4()) + "_" + file.filename
            file.save(os.path.join(UPLOAD_FOLDER, filename))

            conn = sqlite3.connect("notes.db")
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO resources (semester, subject, unit, type, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (semester, subject, unit, rtype, filename))

            conn.commit()
            conn.close()

        return redirect("/admin/dashboard")

    conn = sqlite3.connect("notes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT semester, subject FROM notes")
    subjects = cursor.fetchall()

    cursor.execute("SELECT DISTINCT semester, subject, unit FROM notes")
    units = cursor.fetchall()

    conn.close()

    return render_template("upload_resource.html",
                           semesters=semesters,
                           subjects=subjects,
                           units=units)


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

if __name__ == "__main__":
    app.run(debug=True)