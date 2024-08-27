from app import db, AppUser
from werkzeug.security import generate_password_hash
from app import app

with app.app_context():
    # Admin kullanıcı oluşturma
    admin_email = 'elifsacli@gmail.com'
    admin_password = '159753'
    
    # Önce var olup olmadığını kontrol edin
    existing_admin = AppUser.query.filter_by(email=admin_email).first()
    if not existing_admin:
        admin_user = AppUser(
            email=admin_email,
            password=generate_password_hash(admin_password, method='pbkdf2:sha256'),
            is_admin=True
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Admin kullanıcı başarıyla oluşturuldu.")
    else:
        print("Bu e-posta adresi zaten mevcut.")
