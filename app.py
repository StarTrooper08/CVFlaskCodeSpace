from flask import Flask, render_template,request,flash,redirect,url_for,session,jsonify
import sqlite3
from datetime import datetime
import cv2
import os
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import base64
import tempfile
import json


UPLOAD_FOLDER = '/app/static/uploads/' #pass the upload folder path here(currently passed the container upload folder path)
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])


con=sqlite3.connect("database.db",timeout=5)
cur=con.cursor()                            
cur.execute("create table if not exists user(uid INTEGER PRIMARY KEY,name TEXT, contact TEXT , mail TEXT UNIQUE , password TEXT)")
cur.execute('CREATE table if not exists images (sid INTEGER PRIMARY KEY, user_id INTEGER, filename TEXT, created_at TIMESTAMP)')
con.commit()

app = Flask(__name__)
app.secret_key="123"
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('name') is None or session.get('password') is None:
            flash('Please Login first',category='error')
            return redirect('/login',code=302)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login',methods=["GET","POST"])
def login():
    if request.method == 'POST':
        name=request.form['name']
        password=request.form['password']
        con=sqlite3.connect("database.db")
        user = con.execute('SELECT * FROM user WHERE name = ?', (name,)).fetchone()

        if user:
            if check_password_hash(user[4], password):
                session["uid"] = user[0]
                session["name"] = user[1]
                session["password"] = user[4]
                flash('Logged in successfully!', category='success')
                return redirect(url_for('home'))
            else:
                flash('Incorrect password, try again.', category='error')
        else:
            flash('Email does not exist.', category='error')

        con.close()

    return render_template('index.html')


@app.route('/home',methods=["GET","POST"])
@login_required
def home():
    return render_template("home.html")

def validate_email(mail):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute('SELECT * FROM user WHERE mail = ?', (mail,))
    user = cur.fetchone()
    conn.close()
    if user:
        return False
    return True


@app.route('/register',methods=['GET','POST'])
def register():
    con=sqlite3.connect("database.db")
    cur=con.cursor() 
    if request.method=='POST':
        try:
            name=request.form['name']
            mail=request.form['mail']
            contact=request.form['contact']
            password1=request.form['password1']
            password2=request.form['password2']
            if not validate_email(mail):
                flash('Email already exists.', category='error')
                return redirect(url_for("register"))
            elif not name or not contact or not mail or not password1 or not password2:
                flash('Please fill all the fields.', category='error')
            elif len(mail) < 4:
                flash('Email must be greater than 3 characters.', category='error')
            elif len(name) < 2:
                flash('First name must be greater than 1 character.', category='error')
            elif password1 != password2:
                flash('Passwords don\'t match.', category='error')
            elif len(password1) < 7:
                flash('Password must be at least 7 characters.', category='error')
            else:
                con=sqlite3.connect("database.db")
                cur=con.cursor() 
                password=generate_password_hash(
                password1, method='sha256')            
                cur.execute('INSERT INTO user (name, contact, mail, password) VALUES (?, ?, ?, ?)', (name, contact, mail, password))
                con.commit()
                flash('Record Added Successfully', category='success')
                return redirect(url_for("register"))
        except:
            flash('Error in Insert Operation', category='error')
        finally:
            return redirect(url_for("index"))
            con.close()
                
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route('/gallery',methods=['GET','POST'])
@login_required
def gallery():
    images=display_images()
    return render_template("gallery.html", images=images)

def display_images():
    con = sqlite3.connect('database.db')
    c = con.cursor()
    user_id = session.get('uid')
    c.execute('Select filename from images WHERE user_id=?',(user_id,))
    image_paths = c.fetchall()
    con.close()
    images = []
    for path in image_paths:
        images.append(url_for('static', filename='uploads/' + path[0]))
    return images

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def make_sketch(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9)
    color = cv2.bilateralFilter(img, 9, 250, 250)
    cartoon = cv2.bitwise_and(color, color, mask=edges)
    return cartoon

@app.route('/delete',methods=['POST'])
def delete():   
    filename=request.form['imagetitle']
    con = sqlite3.connect('database.db')
    c = con.cursor()
    c.execute("select * from images where filename=(?)", (filename,) )
    data = c.fetchone()
    dbfileid = data[0]
    dbfilename = data[2]
    print(dbfilename)
    os.unlink(os.path.join(app.config['UPLOAD_FOLDER'], dbfilename))
    c.execute("delete from images where sid=(?)", (dbfileid,) )
    con.commit()
    con.close()
    flash('file successfully deleted',category='success')  
    return render_template('gallery.html')


@app.route('/sketch',methods=['POST'])
def sketch():
    con = sqlite3.connect('database.db')
    c = con.cursor()
    user_id = session.get('uid')
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        img = cv2.imread(UPLOAD_FOLDER+'/'+filename)
        sketch_img = make_sketch(img)
        sketch_img_name = filename.split('.')[0] + '_' + str(user_id) + '_sketch.jpg'
        _ = cv2.imwrite(UPLOAD_FOLDER+'/'+sketch_img_name, sketch_img)
        created_at = datetime.utcnow()
        c.execute('INSERT INTO images (user_id, filename, created_at) VALUES (?, ?, ?)', (user_id, sketch_img_name, created_at))
        con.commit()
        con.close()
        flash('Image Added Successfully', category='success')
        return render_template('home.html',org_img_name=filename,sketch_img_name=sketch_img_name)

if __name__ == '__main__':
    app.run(host ='0.0.0.0', port = 5001, debug = True)