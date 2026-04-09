from flask_login import UserMixin
from werkzeug.security import generate_password_hash,check_password_hash
from database import get_db

class User(UserMixin):
    def __init__(self,id,name,role):
        self.id=id
        self.name=name
        self.role=role

def create_user(name,email,password,role):
    db=get_db()
    db.execute("INSERT INTO users VALUES(NULL,?,?,?,?)",
        (name,email,generate_password_hash(password),role))
    db.commit()
    db.close()

def login_user_auth(email,password):
    db=get_db()
    u=db.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    db.close()
    if u and check_password_hash(u["password"],password):
        return User(u["id"],u["name"],u["role"])
    return None
