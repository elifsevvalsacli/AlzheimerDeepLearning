from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.image import img_to_array, load_img
import numpy as np
from functools import wraps
from metrics.f1_score import F1Score

app = Flask(__name__)

# Sınıf isimleri sözlüğü
verbose_name = {
    0: "Mild Demented",
    1: "Moderate Demented",
    2: "Non Demented",
    3: "Very Mild Demented",
}

# Modeli yükleme
model = load_model('model/vgg19_model.keras', custom_objects={'F1Score': F1Score})
model.make_predict_function()

def predict_label(img_path):
    test_image = load_img(img_path, target_size=(176, 176))
    test_image = img_to_array(test_image) / 255.0
    test_image = np.expand_dims(test_image, axis=0)
    predict_x = model.predict(test_image)
    classes_x = np.argmax(predict_x, axis=1)
    return verbose_name[classes_x[0]]

# Flask uygulama yapılandırması
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://elifsacli:159753@localhost:5432/alzheimerdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# SQLAlchemy nesnesi oluşturuluyor
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Veritabanı modelleri
class AppUser(db.Model):
    __tablename__ = 'app_user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    

    def __init__(self, email, password, is_admin=False):
        self.email = email
        self.password = password
        self.is_admin = is_admin

    def __repr__(self):
        return f'<AppUser {self.email}>'

class UploadedImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    user = db.relationship('AppUser', backref=db.backref('images', lazy=True))
    result = db.Column(db.String(255), nullable=True)  # Tahmin sonuçları

    def __repr__(self):
        return f'<UploadedImage {self.filename}>'


# login_required dekoratörünü tanımlayın
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Lütfen önce giriş yapın.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin kontrolü için dekoratör
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Lütfen önce giriş yapın.', 'danger')
            return redirect(url_for('login'))
        user = AppUser.query.filter_by(email=session['user']).first()
        if not user.is_admin:
            flash('Bu sayfayı görüntüleme izniniz yok.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Fotoğraf bilgilerini veritabanına kaydet
            user = AppUser.query.filter_by(email=session['user']).first()
            result = predict_label(filepath)
            new_image = UploadedImage(filename=filename, filepath=filepath, user_id=user.id, result=result)
            db.session.add(new_image)
            db.session.commit()

            return redirect(url_for('result', filepath=filepath))
    return render_template('index.html')


@app.route('/result')
@login_required
def result():
    filepath = request.args.get('filepath')
    result = predict_label(filepath)
    return render_template('result.html', result=result, filepath=filepath)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Kullanıcıdan 'username' yerine 'email' alıyorsanız, bu adı doğru şekilde kullanmalısınız
        email = request.form.get('email', '')  # 'username' yerine 'email'
        password = request.form.get('password', '')

        if AppUser.query.filter_by(email=email).first():
            flash('Bu e-posta adresi zaten kayıtlı.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = AppUser(email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Kayıt başarılı! Lütfen giriş yapın.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        
        user = AppUser.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user'] = user.email  # E-posta oturumda saklanıyor
            if user.is_admin:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('index'))
        else:
            message = "Geçersiz giriş bilgileri. Lütfen tekrar deneyin."
            return render_template('login.html', message=message)
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('login'))

@app.route('/admin')
@admin_required
def admin_panel():
    images = UploadedImage.query.all()
    return render_template('admin_panel.html', images=images)

# Hakkında Sayfası
@app.route('/hakkinda')
def hakkinda():
    return render_template('hakkinda.html')

if __name__ == '__main__':
    app.run(debug=True)
